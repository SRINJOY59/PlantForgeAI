"""LLM relation extraction shared by every prose-shaped lane (text, manuals,
emails, OCR'd scans). Carries the coreference and negation rules; callers
supply how provenance is built (char spans for prose, pages for manuals)."""

from pydantic import BaseModel, Field

from plantmind_core import tags
from plantmind_core.config import get_settings
from plantmind_core.llm import Tier
from plantmind_core.schemas import CandidateEdge, CandidateNode, EdgeType, NodeType
from plantmind_core.telemetry import get_logger

log = get_logger("extraction.relations")


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
({filename}). Extract only relations the text asserts as actual fact:

- failures: an equipment tag that suffered a real failure mode
- procedures: a named procedure that applies to an equipment tag
- regulations: a standard code (e.g. OISD-STD-119) governing an equipment tag

Tags known to appear in this document: {tag_list}

Reference resolution: when the text says "the pump", "it", "the standby
unit" and similar, resolve it to the most plausible tag from the list above
using context, and report that tag. Never report a tag that is not in the
list.

Do NOT extract from:
- negated statements: "no leakage observed at seal faces" -> nothing
- instructions to inspect or verify: "inspect for cavitation damage" -> nothing
- hypotheticals and conditionals: "if the pump trips, close V-12" -> nothing
- possibilities: "possible bearing wear" -> nothing

Example that SHOULD extract: "P-101A was shut down after the pump began
leaking at the gland" -> failure: P-101A, gland leak.

chunk_index refers to the [chunk N] markers below.

{chunks}"""

# One batch of manual chunks can assert a lot of relations, and the whole batch
# is lost if the answer does not fit - so this call gets a bigger budget than
# structured()'s 4096 default (which doubles it again on a parse failure).
BATCH_MAX_TOKENS = 8192


def ensure_tag_node(nodes: dict, tag: str) -> None:
    node_type = NodeType.INSTRUMENT if tags.is_instrument(tag) \
        else NodeType.EQUIPMENT
    nodes.setdefault((node_type.value, tag), CandidateNode(
        type=node_type, surface_form=tag))


class RelationExtractor:
    def __init__(self, llm, batch_size=None):
        self._llm = llm
        self._batch_size = batch_size or get_settings().extraction_batch_size

    async def run(self, filename, chunks, known_tags, nodes, edges, make_prov):
        """chunks need .index and .text; make_prov(chunk, confidence) builds
        the provenance for a finding located in that chunk."""
        by_index = {c.index: c for c in chunks}
        for i in range(0, len(chunks), self._batch_size):
            batch = chunks[i:i + self._batch_size]
            listing = "\n\n".join(f"[chunk {c.index}]\n{c.text}" for c in batch)
            try:
                findings = await self._llm.structured(
                    [{"role": "user", "content": PROMPT.format(
                        filename=filename,
                        tag_list=", ".join(known_tags) or "none",
                        chunks=listing)}],
                    BatchFindings, tier=Tier.MID, max_tokens=BATCH_MAX_TOKENS)
            except Exception as e:
                # One batch is not the document. A dense stretch of a long
                # manual asserts more relations than the model has room to
                # emit, and it answers with JSON cut off mid-object; letting
                # that raise threw away every batch already read AND the
                # document with them, so a 100-page IOM landed nowhere at all.
                # Skipping the batch costs its relations and keeps the rest -
                # the same trade _outline already makes when its call fails.
                log.warning("relation batch failed, skipping it",
                            filename=filename,
                            chunks=f"{batch[0].index}-{batch[-1].index}",
                            error_type=type(e).__name__, error=str(e)[:200])
                continue
            self._apply(by_index, findings, nodes, edges, make_prov)

    def _apply(self, by_index, findings: BatchFindings, nodes, edges, make_prov):
        def prov(idx, confidence):
            chunk = by_index.get(idx) or next(iter(by_index.values()))
            return make_prov(chunk, confidence)

        for f in findings.failures:
            if not tags.looks_like_tag(f.equipment_tag):
                log.warning("dropped finding with bad tag", tag=f.equipment_tag)
                continue
            tag = tags.normalize(f.equipment_tag)
            ensure_tag_node(nodes, tag)
            mode = f.failure_mode.strip().upper().replace(" ", "-")
            nodes.setdefault(("FailureMode", mode), CandidateNode(
                type=NodeType.FAILURE_MODE, surface_form=mode,
                props={"cause": f.cause} if f.cause else {}))
            edges.append(CandidateEdge(
                type=EdgeType.HAS_FAILURE, src=tag, dst=mode,
                provenance=prov(f.chunk_index, f.confidence),
                props={"cause": f.cause} if f.cause else {}))

        for p in findings.procedures:
            if not tags.looks_like_tag(p.equipment_tag):
                continue
            tag = tags.normalize(p.equipment_tag)
            ensure_tag_node(nodes, tag)
            name = p.procedure_name.strip()
            nodes.setdefault(("Procedure", name), CandidateNode(
                type=NodeType.PROCEDURE, surface_form=name))
            edges.append(CandidateEdge(
                type=EdgeType.FIXED_BY, src=tag, dst=name,
                provenance=prov(p.chunk_index, p.confidence)))

        for r in findings.regulations:
            if not tags.looks_like_tag(r.equipment_tag):
                continue
            tag = tags.normalize(r.equipment_tag)
            ensure_tag_node(nodes, tag)
            std = r.standard.strip().upper()
            nodes.setdefault(("RegulationClause", std), CandidateNode(
                type=NodeType.REGULATION_CLAUSE, surface_form=std))
            edges.append(CandidateEdge(
                type=EdgeType.GOVERNED_BY, src=tag, dst=std,
                provenance=prov(r.chunk_index, r.confidence)))
