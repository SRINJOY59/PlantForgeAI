from pydantic import BaseModel, Field

from plantmind_core import tags
from plantmind_core.config import get_settings
from plantmind_core.llm import Tier
from plantmind_core.schemas import (
    CandidateEdge, CandidateNode, CandidateSubgraph, EdgeType, NodeType, Provenance,
)
from plantmind_core.telemetry import get_logger

from extraction.text.chunker import SectionChunker

log = get_logger("extraction.text")

EXTRACTOR_VERSION = "text-v1"


class FailureFinding(BaseModel):
    chunk_index: int
    equipment_tag: str
    failure_mode: str
    cause: str = ""
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class ProcedureFinding(BaseModel):
    chunk_index: int
    equipment_tag: str
    procedure_name: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class RegulationFinding(BaseModel):
    chunk_index: int
    equipment_tag: str
    standard: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class BatchFindings(BaseModel):
    failures: list[FailureFinding] = []
    procedures: list[ProcedureFinding] = []
    regulations: list[RegulationFinding] = []


PROMPT = """You are reading chunks of an industrial plant document
(SOP, incident report or manual). Extract only what is explicitly stated:

- failures: an equipment tag suffering a failure mode (e.g. seal leak, trip)
- procedures: a named procedure that applies to an equipment tag
- regulations: a standard/regulation code (e.g. OISD-STD-119) governing a tag

Use exact equipment tags as written (like P-101A). Skip anything without a
concrete tag. chunk_index refers to the numbers below.

{chunks}"""


class TextExtractor:
    def __init__(self, llm, embedder, chunker=None):
        self._llm = llm
        self._embedder = embedder
        self._chunker = chunker or SectionChunker()
        self._batch_size = get_settings().extraction_batch_size

    async def extract(self, doc_id: str, content_hash: str, filename: str,
                      text: str) -> CandidateSubgraph:
        chunks = self._chunker.split(text)
        if not chunks:
            raise ValueError(f"{filename}: no extractable text")

        nodes = {("Document", doc_id): CandidateNode(
            type=NodeType.DOCUMENT, surface_form=doc_id,
            props={"filename": filename, "content_hash": content_hash})}
        edges = []

        embeddings = await self._embedder.embed([c.text for c in chunks])
        for chunk, emb in zip(chunks, embeddings):
            chunk_id = f"{doc_id}#chunk{chunk.index}"
            nodes[("Chunk", chunk_id)] = CandidateNode(
                type=NodeType.CHUNK, surface_form=chunk_id,
                props={"text": chunk.text, "section": chunk.section,
                       "start": chunk.start, "end": chunk.end,
                       "embedding": emb})
            edges.append(CandidateEdge(
                type=EdgeType.PART_OF, src=chunk_id, dst=doc_id,
                provenance=self._prov(doc_id, chunk.start, chunk.end, 1.0)))

        self._mention_pass(doc_id, text, nodes, edges)
        await self._llm_pass(doc_id, chunks, nodes, edges)

        return CandidateSubgraph(doc_id=doc_id, content_hash=content_hash,
                                 nodes=list(nodes.values()), edges=edges)

    # deterministic layer: every tag-shaped string becomes a mention edge
    def _mention_pass(self, doc_id, text, nodes, edges):
        seen_spans = set()
        for tag, start, end in tags.find_tags(text):
            self._tag_node(nodes, tag)
            if tag not in seen_spans:      # one mention edge per tag per doc
                seen_spans.add(tag)
                edges.append(CandidateEdge(
                    type=EdgeType.MENTIONED_IN, src=tag, dst=doc_id,
                    provenance=self._prov(doc_id, start, end, 1.0)))

    # judgment layer: relationships need the model
    async def _llm_pass(self, doc_id, chunks, nodes, edges):
        for i in range(0, len(chunks), self._batch_size):
            batch = chunks[i:i + self._batch_size]
            listing = "\n\n".join(f"[chunk {c.index}]\n{c.text}" for c in batch)
            findings = await self._llm.structured(
                [{"role": "user", "content": PROMPT.format(chunks=listing)}],
                BatchFindings, tier=Tier.MID)
            self._apply(doc_id, chunks, findings, nodes, edges)

    def _apply(self, doc_id, chunks, findings: BatchFindings, nodes, edges):
        def span(idx):
            c = chunks[idx] if 0 <= idx < len(chunks) else None
            return (c.start, c.end) if c else (0, 0)

        for f in findings.failures:
            if not tags.looks_like_tag(f.equipment_tag):
                log.warning("dropped finding with bad tag", tag=f.equipment_tag)
                continue
            tag = tags.normalize(f.equipment_tag)
            self._tag_node(nodes, tag)
            mode = f.failure_mode.strip().upper().replace(" ", "-")
            nodes.setdefault(("FailureMode", mode), CandidateNode(
                type=NodeType.FAILURE_MODE, surface_form=mode,
                props={"cause": f.cause} if f.cause else {}))
            edges.append(CandidateEdge(
                type=EdgeType.HAS_FAILURE, src=tag, dst=mode,
                provenance=self._prov(doc_id, *span(f.chunk_index), f.confidence),
                props={"cause": f.cause} if f.cause else {}))

        for p in findings.procedures:
            if not tags.looks_like_tag(p.equipment_tag):
                continue
            tag = tags.normalize(p.equipment_tag)
            self._tag_node(nodes, tag)
            name = p.procedure_name.strip()
            nodes.setdefault(("Procedure", name), CandidateNode(
                type=NodeType.PROCEDURE, surface_form=name))
            edges.append(CandidateEdge(
                type=EdgeType.FIXED_BY, src=tag, dst=name,
                provenance=self._prov(doc_id, *span(p.chunk_index), p.confidence)))

        for r in findings.regulations:
            if not tags.looks_like_tag(r.equipment_tag):
                continue
            tag = tags.normalize(r.equipment_tag)
            self._tag_node(nodes, tag)
            std = r.standard.strip().upper()
            nodes.setdefault(("RegulationClause", std), CandidateNode(
                type=NodeType.REGULATION_CLAUSE, surface_form=std))
            edges.append(CandidateEdge(
                type=EdgeType.GOVERNED_BY, src=tag, dst=std,
                provenance=self._prov(doc_id, *span(r.chunk_index), r.confidence)))

    @staticmethod
    def _tag_node(nodes, tag):
        node_type = NodeType.INSTRUMENT if tags.is_instrument(tag) \
            else NodeType.EQUIPMENT
        nodes.setdefault((node_type.value, tag), CandidateNode(
            type=node_type, surface_form=tag))

    @staticmethod
    def _prov(doc_id, start, end, confidence):
        return Provenance(doc_id=doc_id, span=(start, end),
                          extractor_version=EXTRACTOR_VERSION,
                          confidence=confidence)
