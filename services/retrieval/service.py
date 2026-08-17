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

    async def ask(self, question: str, history: list | None = None, alert_context: str | None = None) -> Answer:
        question = await self._condenser.condense(question, history or [])
        embedding = await self._embed(question)
        
        # Bypass cache on alert-scoped chat
        cached = None if alert_context else await asyncio.to_thread(self._cache_get, embedding)
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
            version, prepared.corrections)
        await asyncio.to_thread(self._name_citations, answer)
        await asyncio.to_thread(
            self._cache_put, question, embedding, answer, prepared.cited)
        return answer

    async def ask_stream(self, question: str, history: list | None = None, alert_context: str | None = None):
        """Yields ('token', text) deltas while generating, then a final
        ('done', Answer). A cache hit streams the cached text so the client
        path is identical."""
        # everything below - the cache key included - is about the standalone
        # question, never the words the user typed into a thread
        question = await self._condenser.condense(question, history or [])
        embedding = await self._embed(question)
        
        # Bypass cache on alert-scoped chat
        cached = None if alert_context else await asyncio.to_thread(self._cache_get, embedding)
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
        async for delta in self._answerer.stream(question, context_to_use):
            chunks.append(delta)
            yield "token", delta
        # the finished text, not an empty envelope: grounding is read out of
        # what the answer cited, so it cannot be decided before it exists
        version = await asyncio.to_thread(self._graph_version)
        answer = self._answerer.build_meta(
            "".join(chunks), prepared.evidence, prepared.mode,
            version, prepared.corrections)
        await asyncio.to_thread(self._name_citations, answer)
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

        digest = self._plant_digest(question)
        if digest:
            context = digest + "\n\n" + context

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

    def _local_context(self, seed, embedding: list):
        relations = self._reader.relations_of(seed.node_id, LOCAL_TYPES)
        rel_lines, edge_evidence, seen = [], [], set()
        for r in relations:
            facts = {**r["props"], **(r.get("other_props") or {})}
            notes = ", ".join(f"{k}: {facts[k]}" for k in NOTE_KEYS
                              if facts.get(k) not in (None, ""))
            rel_lines.append(f"  ({seed.surface}) -{r['type']}"
                             + (f" ({notes})" if notes else "")
                             + f"- ({r['other_surface']} [{r['other_label']}])")
            doc_id = r["props"].get("doc_id")
            if doc_id and doc_id not in seen:      # tables cite their rows
                seen.add(doc_id)
                edge_evidence.append(Evidence(
                    doc_id=doc_id, text=rel_lines[-1].strip(),
                    page=r["props"].get("page"),
                    chunk_id=f"edge:{doc_id}:{r['type']}"))

        # hybrid: exact-text mentions AND semantic matches - the chunk that
        # answers may never name the tag (e.g. torque steps inside its SOP)
        chunks = {c["id"]: c for c in self._reader.chunks_containing(seed.surface)}
        for c in self._reader.vector_chunks(embedding, k=4):
            chunks.setdefault(c["id"], c)
        chunk_evidence = [Evidence(doc_id=_doc_of(c["id"]), text=c["text"],
                                   context=c.get("context") or "",
                                   page=c.get("page"), chunk_id=c["id"])
                          for c in chunks.values()]

        evidence = (chunk_evidence + edge_evidence)[:10]
        context = (f"EVERYTHING THE GRAPH KNOWS ABOUT {seed.surface}:\n"
                   + "\n".join(rel_lines))
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

        # structure alone isn't enough: the narrative behind the topology
        # (incident timelines, SOP steps) lives in chunks
        seen = {e.chunk_id for e in evidence}
        extra = [Evidence(doc_id=_doc_of(c["id"]), text=c["text"],
                          context=c.get("context") or "",
                          page=c.get("page"), chunk_id=c["id"])
                 for c in self._reader.vector_chunks(embedding, k=3)
                 if c["id"] not in seen]
        if extra:
            context += "\n\nRELATED PASSAGES:\n\n" + "\n\n".join(
                f"[{e.doc_id}]\n" + e.context + e.text[:600] for e in extra)
            evidence = evidence + extra
        return context, evidence

    def _plant_digest(self, question: str) -> str:
        if not any(w in question.lower() for w in DIGEST_WORDS):
            return ""
        from datetime import date
        lines = []
        overdue = self._reader.overdue_inspections(date.today().isoformat())
        if overdue:
            lines.append("Inspections past their due date:")
            lines += [f"  {r['equipment']}: {r['inspection_type']} per "
                      f"{r['standard']}, was due {r['next_due']} "
                      f"[doc:{r['doc_id']}]" for r in overdue]
        counts = self._reader.failure_mode_counts()
        if counts:
            lines.append("Failure modes by work-order count:")
            lines += [f"  {r['mode']}: {r['n']} (on {', '.join(r['equipment'])})"
                      for r in counts]
        return "PLANT DIGEST (live graph queries):\n" + "\n".join(lines) \
            if lines else ""

    def graph_snapshot(self, limit: int = 400) -> dict:
        return self._reader.graph_snapshot(limit)

    # ------------------------------------------------------------- helpers
    async def _embed(self, text: str) -> list:
        (embedding,) = await self._embedder.embed([text])
        return embedding

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
