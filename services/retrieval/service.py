import asyncio
from dataclasses import dataclass, field

from plantmind_core.schemas import Answer, CorrectionNote, QueryMode
from plantmind_core.telemetry import get_logger

from retrieval.answerer import Answerer
from retrieval.assembler import ContextAssembler
from retrieval.condenser import QuestionCondenser
from retrieval.linker import QueryLinker
from retrieval.models import Evidence
from retrieval.pathfinder import PathFinder
from retrieval.pruner import FlowPruner
from retrieval.router import ModeRouter

log = get_logger("retrieval.service")

LOCAL_TYPES = ["CONNECTED_TO", "HAS_FAILURE", "FIXED_BY", "GOVERNED_BY",
               "MENTIONED_IN"]
NOTE_KEYS = ("cause", "wo_id", "date", "next_due", "result",
             "inspection_type", "remarks", "description", "action_taken",
             "downtime_hours", "technician", "title")

# aggregate/compliance questions need plant-wide graph facts that no chunk
# carries (they live in table-derived edges); these words trigger a digest
DIGEST_WORDS = ("overdue", "statutory", "inspection", "compliance",
                "most frequent", "most common", "how many", "which equipment")

from retrieval.answerer import Answerer, _resolve_persona


def _cacheable(alert_context, persona) -> bool:
    if alert_context:
        return False
    # Only cache the generic engineer persona. Tone-shifted personas (worker,
    # operator, instrumentation, process, planner, inspection, hse, admin)
    # always generate fresh answers reflecting their specific register and focus.
    return _resolve_persona(persona) == "engineer"


@dataclass
class Prepared:
    """Everything retrieval worked out before a token was generated. A tuple
    stopped being readable at four fields and this needed a fifth."""
    mode: QueryMode
    context: str
    evidence: list
    cited: list
    corrections: list = field(default_factory=list)


class RetrievalService:
    """Three retrieval modes behind one ask(): vector for single facts,
    local for asset-centric questions, PathRAG for causal/multi-entity
    reasoning. The router picks; every mode ends in the same answerer. A
    semantic answer cache short-circuits repeated questions.

    A follow-up is condensed into a standalone question before any of that
    runs, so the rest of the pipeline never has to know a conversation
    existed."""

    def __init__(self, reader, llm, embedder, bus=None, cache=None):
        self._reader = reader
        self._embedder = embedder
        self._bus = bus
        self._cache = cache
        self._condenser = QuestionCondenser(llm)
        self._linker = QueryLinker(reader)
        self._router = ModeRouter()
        self._pathfinder = PathFinder(reader)
        self._pruner = FlowPruner()
        self._assembler = ContextAssembler(reader)
        self._answerer = Answerer(llm)

    @classmethod
    def from_settings(cls) -> "RetrievalService":
        from plantmind_core.bus import RedisBus
        from plantmind_core.cache import AnswerCache
        from plantmind_core.llm import get_embedder, get_llm

        from retrieval.graph_reader import GraphReader

        return cls(GraphReader.from_settings(), get_llm(), get_embedder(),
                   bus=RedisBus.from_settings(),
                   cache=AnswerCache.from_settings())

    async def ask(self, question: str, history: list | None = None,
                  alert_context: str | None = None,
                  persona: str | None = None) -> Answer:
        question = await self._condenser.condense(question, history or [])
        embedding = await self._embed(question)
        
        # Bypass cache on alert-scoped chat and for tone-shifted personas
        cacheable = _cacheable(alert_context, persona)
        cached = await asyncio.to_thread(self._cache_get, embedding) if cacheable else None
        if cached:
            # name here too: entries cached before filenames existed, and every
            # future cache-format change, would otherwise surface as raw hashes
            await asyncio.to_thread(self._name_citations, cached)
            return cached

        # the graph-read pipeline is synchronous (the Neo4j driver is sync), so
        # run it off the event loop - otherwise every user's reads block every
        # other user's request, LLM streams included
        prepared = await asyncio.to_thread(self._prepare, question, embedding)

        context_to_use = prepared.context
        if alert_context:
            context_to_use = f"CURRENT ALERT CONTEXT:\n{alert_context}\n\n" + context_to_use

        version = await asyncio.to_thread(self._graph_version)
        answer = await self._answerer.answer(
            question, context_to_use, prepared.evidence, prepared.mode,
            version, prepared.corrections, persona=persona)
        await asyncio.to_thread(self._name_citations, answer)
        if cacheable:
            await asyncio.to_thread(
                self._cache_put, question, embedding, answer, prepared.cited)
        return answer

    async def ask_stream(self, question: str, history: list | None = None,
                         alert_context: str | None = None,
                         persona: str | None = None):
        """Yields ('token', text) deltas while generating, then a final
        ('done', Answer). A cache hit streams the cached text so the client
        path is identical."""
        # everything below - the cache key included - is about the standalone
        # question, never the words the user typed into a thread
        question = await self._condenser.condense(question, history or [])
        embedding = await self._embed(question)
        
        # Bypass cache on alert-scoped chat and for tone-shifted personas
        cacheable = _cacheable(alert_context, persona)
        cached = await asyncio.to_thread(self._cache_get, embedding) if cacheable else None
        if cached:
            await asyncio.to_thread(self._name_citations, cached)
            yield "token", cached.text
            yield "done", cached
            return

        # off the event loop: the sync Neo4j reads must not stall other users
        prepared = await asyncio.to_thread(self._prepare, question, embedding)
        
        context_to_use = prepared.context
        if alert_context:
            context_to_use = f"CURRENT ALERT CONTEXT:\n{alert_context}\n\n" + context_to_use

        chunks = []
        async for delta in self._answerer.stream(question, context_to_use,
                                                 persona=persona):
            chunks.append(delta)
            yield "token", delta
        # the finished text, not an empty envelope: grounding is read out of
        # what the answer cited, so it cannot be decided before it exists
        version = await asyncio.to_thread(self._graph_version)
        answer = self._answerer.build_meta(
            "".join(chunks), prepared.evidence, prepared.mode,
            version, prepared.corrections)
        await asyncio.to_thread(self._name_citations, answer)
        if cacheable:
            await asyncio.to_thread(
                self._cache_put, question, embedding, answer, prepared.cited)
        yield "done", answer

    def _name_citations(self, answer: Answer):
        """Fill each citation's display name from the graph. Runs after the
        answer is whole and touches only the filename field - the doc_id, the
        prompt and the grounding are untouched, so this cannot change what the
        answer says, only how a source reads on screen."""
        names = self._reader.document_names({c.doc_id for c in answer.citations})
        for c in answer.citations:
            c.filename = names.get(c.doc_id) or names.get(f"doc:{c.doc_id}")

    def _prepare(self, question: str, embedding: list) -> "Prepared":
        """The whole retrieval pipeline up to (not including) generation.

        Synchronous on purpose: every step here is a blocking Neo4j read on the
        sync driver, so callers run it via asyncio.to_thread to keep the event
        loop free for other in-flight requests."""
        seeds = self._linker.link(question)
        mode = self._router.route(question, seeds)
        log.info("routing", mode=mode.value, seeds=len(seeds))

        if mode == QueryMode.VECTOR:
            context, evidence = self._vector_context(embedding)
        elif mode == QueryMode.LOCAL:
            context, evidence = self._local_context(seed=seeds[0],
                                                    embedding=embedding)
        else:
            context, evidence = self._path_context(question, seeds, embedding)
            if not context:                        # no paths at all: degrade
                mode = QueryMode.VECTOR
                context, evidence = self._vector_context(embedding)

        digest, digest_evidence = self._plant_digest(question)
        if digest:
            context = digest + "\n\n" + context
            # The digest cites documents (inspection records, work-order tables)
            # that no chunk carries. Without adding them to evidence, their
            # citations can't be resolved to a filename and the answer grades
            # "unverified" - so fold them in, skipping any doc already present.
            seen = {e.doc_id for e in evidence}
            evidence = evidence + [e for e in digest_evidence
                                   if e.doc_id and e.doc_id not in seen]

        corrections = self._corrections(evidence)
        if corrections:
            # first in the prompt, above the material it overrules. A
            # correction is the highest tier we have, and a model that reads it
            # last has already formed the answer the correction exists to
            # prevent.
            context = _corrections_block(corrections) + "\n\n" + context

        cited = ([s.node_id for s in seeds]
                 + [f"doc:{e.doc_id}" for e in evidence])
        return Prepared(mode=mode, context=context, evidence=evidence,
                        cited=cited, corrections=corrections)

    def _corrections(self, evidence: list) -> list:
        rows = self._reader.corrections_of({e.doc_id for e in evidence})
        if rows:
            log.info("evidence includes corrected documents",
                     docs=[r["doc_id"] for r in rows])
        return [CorrectionNote(doc_id=r["doc_id"],
                               correction_id=r["correction_id"],
                               author=r["author"] or "an engineer",
                               text=r["correction"] or "")
                for r in rows]

    # ---------------------------------------------------------------- modes
    def _vector_context(self, embedding: list):
        chunks = self._reader.vector_chunks(embedding)
        evidence = [Evidence(doc_id=_doc_of(c["id"]), text=c["text"],
                             context=c.get("context") or "",
                             page=c.get("page"), chunk_id=c["id"])
                    for c in chunks]
        context = "SOURCE PASSAGES:\n\n" + "\n\n".join(
            f"[{e.doc_id}" + (f" p{e.page}" if e.page else "") + "]\n"
            + e.context + e.text for e in evidence)
        return context, evidence

    def _seed_history(self, seeds: list) -> tuple[str, list[Evidence]]:
        """Pull detailed failure history, work orders, actions taken, and
        exact document mentions for all seed equipment. Ensures Ask has full
        recall on root causes, symptoms, and maintenance events."""
        if not seeds:
            return "", []
        blocks, evidence, seen_docs = [], [], set()

        for seed in seeds:
            wos = self._reader.equipment_work_orders(seed.node_id)
            failures = self._reader.equipment_failures(seed.node_id)
            if not wos and not failures:
                continue

            lines = [f"MAINTENANCE & FAILURE HISTORY FOR {seed.surface}:"]
            if failures:
                for f in failures:
                    causes = f" (causes noted: {', '.join(f['causes'])})" if f.get("causes") else ""
                    lines.append(f"  • Failure Mode: {f['mode']} — Total occurrences in graph: {f['count']}{causes}")
            if wos:
                lines.append(f"  • Chronological Work Orders ({len(wos)} events):")
                for w in wos:
                    doc_id = w.get("doc_id")
                    cite = f" [doc:{doc_id}]" if doc_id else ""
                    action = f" | Action Taken: {w['action_taken']}" if w.get("action_taken") else ""
                    downtime = f" ({w['downtime_hours']}h downtime)" if w.get("downtime_hours") else ""
                    tech = f" (Tech: {w['technician']})" if w.get("technician") else ""
                    wo_line = f"    - {w.get('date', 'Unknown date')} [{w['wo_id']}]: {w.get('description', '')}{action}{downtime}{tech}{cite}"
                    lines.append(wo_line)
                    if doc_id and doc_id not in seen_docs:
                        seen_docs.add(doc_id)
                        evidence.append(Evidence(
                            doc_id=doc_id, text=wo_line.strip(),
                            page=1, chunk_id=f"wo:{w['wo_id']}:{doc_id}"))

            blocks.append("\n".join(lines))

        return "\n\n".join(blocks), evidence

    def _local_context(self, seed, embedding: list):
        relations = self._reader.relations_of(seed.node_id, LOCAL_TYPES)
        rel_lines, edge_evidence, seen = [], [], set()
        for r in relations:
            facts = {**r["props"], **(r.get("other_props") or {})}
            notes = ", ".join(f"{k}: {facts[k]}" for k in NOTE_KEYS
                              if facts.get(k) not in (None, ""))
            doc_id = r["props"].get("doc_id")
            doc_tag = f" [doc:{doc_id}]" if doc_id else ""
            rel_lines.append(f"  ({seed.surface}) -{r['type']}"
                             + (f" ({notes})" if notes else "")
                             + f"- ({r['other_surface']} [{r['other_label']}])"
                             + doc_tag)
            if doc_id and doc_id not in seen:      # tables cite their rows
                seen.add(doc_id)
                edge_evidence.append(Evidence(
                    doc_id=doc_id, text=rel_lines[-1].strip(),
                    page=r["props"].get("page"),
                    chunk_id=f"edge:{doc_id}:{r['type']}"))

        hist_text, hist_ev = self._seed_history([seed])

        # hybrid: exact-text mentions AND semantic matches - the chunk that
        # answers may never name the tag (e.g. torque steps inside its SOP)
        chunks = {c["id"]: c for c in self._reader.chunks_containing(seed.surface)}
        for c in self._reader.vector_chunks(embedding, k=4):
            chunks.setdefault(c["id"], c)
        chunk_evidence = [Evidence(doc_id=_doc_of(c["id"]), text=c["text"],
                                   context=c.get("context") or "",
                                   page=c.get("page"), chunk_id=c["id"])
                          for c in chunks.values()]

        evidence = (hist_ev + chunk_evidence + edge_evidence)[:15]
        context = (f"EVERYTHING THE GRAPH KNOWS ABOUT {seed.surface}:\n"
                   + "\n".join(rel_lines))
        if hist_text:
            context = hist_text + "\n\n" + context
        if chunk_evidence:
            context += "\n\nSOURCE PASSAGES:\n\n" + "\n\n".join(
                f"[{e.doc_id}]\n" + e.context + e.text[:600]
                for e in chunk_evidence)
        return context, evidence

    def _path_context(self, question: str, seeds, embedding: list):
        paths, degrees = self._pathfinder.find(question, seeds)
        if not paths:
            return "", []
        kept = self._pruner.prune(paths, degrees)
        log.info("paths", candidates=len(paths), kept=len(kept))
        context, evidence = self._assembler.build(kept)

        # Asset history enrichment: ensure work orders, failure counts, and
        # symptom narratives are visible during causal/root-cause reasoning
        hist_text, hist_ev = self._seed_history(seeds)
        if hist_text:
            context = hist_text + "\n\n" + context
            evidence = hist_ev + evidence

        # Exact text matches for seed tags (incident reports, emails, procedures)
        seen = {e.chunk_id for e in evidence}
        seed_chunks = []
        for s in seeds[:2]:
            for c in self._reader.chunks_containing(s.surface, limit=4):
                if c["id"] not in seen:
                    seen.add(c["id"])
                    seed_chunks.append(Evidence(
                        doc_id=_doc_of(c["id"]), text=c["text"],
                        context=c.get("context") or "",
                        page=c.get("page"), chunk_id=c["id"]))

        vector_chunks = [Evidence(doc_id=_doc_of(c["id"]), text=c["text"],
                                  context=c.get("context") or "",
                                  page=c.get("page"), chunk_id=c["id"])
                         for c in self._reader.vector_chunks(embedding, k=3)
                         if c["id"] not in seen]

        extra = seed_chunks + vector_chunks
        if extra:
            context += "\n\nRELATED PASSAGES:\n\n" + "\n\n".join(
                f"[{e.doc_id}]\n" + e.context + e.text[:600] for e in extra)
            evidence = evidence + extra
        return context, evidence

    def _plant_digest(self, question: str) -> tuple[str, list]:
        """-> (digest_text, digest_evidence).

        The evidence is the second return, not a side effect, because the docs
        the digest names (inspection tables, work-order rows) are cited in the
        answer but live in table-derived edges no chunk carries. Returning them
        as Evidence lets the citation pipeline resolve them to filenames and
        grade the answer grounded, instead of leaving raw hashes and "unverified".
        """
        if not any(w in question.lower() for w in DIGEST_WORDS):
            return "", []
        from datetime import date
        lines, evidence = [], []
        overdue = self._reader.overdue_inspections(date.today().isoformat())
        if overdue:
            lines.append("Inspections past their due date:")
            for r in overdue:
                line = (f"  {r['equipment']}: {r['inspection_type']} per "
                        f"{r['standard']}, was due {r['next_due']} "
                        f"[doc:{r['doc_id']}]")
                lines.append(line)
                if r.get("doc_id"):
                    evidence.append(Evidence(
                        doc_id=r["doc_id"], text=line.strip(),
                        page=r.get("page"), chunk_id=f"digest:{r['doc_id']}"))
        counts = self._reader.failure_mode_counts()
        if counts:
            lines.append("Failure modes by work-order count:")
            for r in counts:
                lines.append(f"  {r['mode']}: {r['n']} "
                             f"(on {', '.join(r['equipment'])})"
                             + (f" [doc:{r['doc_id']}]" if r.get("doc_id") else ""))
                if r.get("doc_id"):
                    evidence.append(Evidence(
                        doc_id=r["doc_id"], text=f"{r['mode']}: {r['n']}",
                        chunk_id=f"digest:{r['doc_id']}"))
        if not lines:
            return "", []
        return "PLANT DIGEST (live graph queries):\n" + "\n".join(lines), evidence

    def graph_snapshot(self, limit: int = 400) -> dict:
        return self._reader.graph_snapshot(limit)

    # ------------------------------------------------------------- helpers
    async def _embed(self, text: str) -> list:
        try:
            results = await self._embedder.embed([text])
            if results:
                return results[0]
        except Exception as e:
            log.warning("Embedding generation error, using zero fallback", error=str(e))
        return [0.0] * 1536

    def _cache_get(self, embedding: list):
        if not self._cache:
            return None
        hit = self._cache.get(embedding)
        if hit:
            log.info("answer cache hit")
            return Answer.model_validate(hit)
        return None

    def _cache_put(self, question, embedding, answer: Answer, cited: list):
        if self._cache:
            self._cache.put(question, embedding, answer.model_dump(mode="json"),
                            cited)

    def _graph_version(self) -> int:
        return self._bus.graph_version() if self._bus else 0


def _corrections_block(corrections: list) -> str:
    lines = ["CORRECTIONS FROM ENGINEERS AT THIS PLANT",
             "These override the passages below. Where a source and a "
             "correction disagree, the correction is right - say so in the "
             "answer, and cite the correction.", ""]
    for c in corrections:
        lines.append(f"  [doc:{c.doc_id}] was corrected by {c.author} "
                     f"[doc:{c.correction_id}]:")
        lines.append(f"    \"{c.text}\"")
    return "\n".join(lines)


def _doc_of(chunk_id: str) -> str:
    # chunk ids look like chunk:<doc_id>#chunkN
    return chunk_id.removeprefix("chunk:").split("#", 1)[0]
