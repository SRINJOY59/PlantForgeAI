from plantmind_core.schemas import Answer, QueryMode
from plantmind_core.telemetry import get_logger

from retrieval.answerer import Answerer
from retrieval.assembler import ContextAssembler
from retrieval.linker import QueryLinker
from retrieval.models import Evidence
from retrieval.pathfinder import PathFinder
from retrieval.pruner import FlowPruner
from retrieval.router import ModeRouter

log = get_logger("retrieval.service")

LOCAL_TYPES = ["CONNECTED_TO", "HAS_FAILURE", "FIXED_BY", "GOVERNED_BY",
               "MENTIONED_IN"]


class RetrievalService:
    """Three retrieval modes behind one ask(): vector for single facts,
    local for asset-centric questions, PathRAG for causal/multi-entity
    reasoning. The router picks; every mode ends in the same answerer."""

    def __init__(self, reader, llm, embedder, bus=None):
        self._reader = reader
        self._embedder = embedder
        self._bus = bus
        self._linker = QueryLinker(reader)
        self._router = ModeRouter()
        self._pathfinder = PathFinder(reader)
        self._pruner = FlowPruner()
        self._assembler = ContextAssembler(reader)
        self._answerer = Answerer(llm)

    @classmethod
    def from_settings(cls) -> "RetrievalService":
        from plantmind_core.bus import RedisBus
        from plantmind_core.llm import get_embedder, get_llm

        from retrieval.graph_reader import GraphReader

        return cls(GraphReader.from_settings(), get_llm(), get_embedder(),
                   bus=RedisBus.from_settings())

    async def ask(self, question: str) -> Answer:
        seeds = self._linker.link(question)
        mode = self._router.route(question, seeds)
        log.info("routing", mode=mode.value, seeds=len(seeds))

        if mode == QueryMode.VECTOR:
            context, evidence = await self._vector_context(question)
        elif mode == QueryMode.LOCAL:
            context, evidence = self._local_context(seeds[0])
        else:
            context, evidence = self._path_context(question, seeds)
            if not evidence:                       # no usable paths: degrade
                mode = QueryMode.VECTOR
                context, evidence = await self._vector_context(question)

        return await self._answerer.answer(question, context, evidence,
                                           mode, self._graph_version())

    # ---------------------------------------------------------------- modes
    async def _vector_context(self, question: str):
        (embedding,) = await self._embedder.embed([question])
        chunks = self._reader.vector_chunks(embedding)
        evidence = [Evidence(doc_id=_doc_of(c["id"]), text=c["text"],
                             context=c.get("context") or "",
                             page=c.get("page"), chunk_id=c["id"])
                    for c in chunks]
        context = "SOURCE PASSAGES:\n\n" + "\n\n".join(
            f"[{e.doc_id}" + (f" p{e.page}" if e.page else "") + "]\n"
            + e.context + e.text for e in evidence)
        return context, evidence

    def _local_context(self, seed):
        relations = self._reader.relations_of(seed.node_id, LOCAL_TYPES)
        rel_lines = []
        for r in relations:
            notes = ", ".join(f"{k}: {v}" for k, v in r["props"].items()
                              if k in ("cause", "wo_id", "date", "next_due",
                                       "result", "inspection_type"))
            rel_lines.append(f"  ({seed.surface}) -{r['type']}"
                             + (f" ({notes})" if notes else "")
                             + f"- ({r['other_surface']} [{r['other_label']}])")

        chunks = self._reader.chunks_containing(seed.surface)
        evidence = [Evidence(doc_id=_doc_of(c["id"]), text=c["text"],
                             context=c.get("context") or "",
                             page=c.get("page"), chunk_id=c["id"])
                    for c in chunks]

        context = (f"EVERYTHING THE GRAPH KNOWS ABOUT {seed.surface}:\n"
                   + "\n".join(rel_lines))
        if evidence:
            context += "\n\nSOURCE PASSAGES:\n\n" + "\n\n".join(
                f"[{e.doc_id}]\n" + e.context + e.text[:600] for e in evidence)
        return context, evidence

    def _path_context(self, question: str, seeds):
        paths, degrees = self._pathfinder.find(question, seeds)
        if not paths:
            return "", []
        kept = self._pruner.prune(paths, degrees)
        log.info("paths", candidates=len(paths), kept=len(kept))
        return self._assembler.build(kept)

    def _graph_version(self) -> int:
        return self._bus.graph_version() if self._bus else 0


def _doc_of(chunk_id: str) -> str:
    # chunk ids look like chunk:<doc_id>#chunkN
    return chunk_id.removeprefix("chunk:").split("#", 1)[0]
