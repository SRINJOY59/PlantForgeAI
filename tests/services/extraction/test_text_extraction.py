import asyncio

import pytest

from plantmind_core.schemas import EdgeType, NodeType
from extraction.text.chunker import SectionChunker
from extraction.text.extractor import (
    BatchFindings, FailureFinding, ProcedureFinding, TextExtractor,
)
from conftest import SAMPLES, FakeEmbedder, FakeLLM

SOP = (SAMPLES / "sop_pump_seal_replacement.md").read_text(encoding="utf-8")


def test_chunker_splits_on_headers_with_true_offsets():
    chunks = SectionChunker().split(SOP)

    assert len(chunks) >= 5
    sections = {c.section for c in chunks}
    assert "1. Safety prerequisites" in sections
    assert "4. Pre-start checks" in sections
    for c in chunks:
        assert SOP[c.start:c.end].strip() == c.text   # offsets point home


def extract(llm_responses):
    llm = FakeLLM(*llm_responses)
    extractor = TextExtractor(llm, FakeEmbedder())
    csg = asyncio.run(extractor.extract("doc-sop", "hash-sop", "sop.md", SOP))
    return csg, llm


def n_batches():
    chunker = SectionChunker()
    from plantmind_core.config import get_settings
    bs = get_settings().extraction_batch_size
    n = len(chunker.split(SOP))
    return -(-n // bs)


def empty_batches():
    return [BatchFindings() for _ in range(n_batches())]


def test_chunks_become_nodes_with_embeddings():
    csg, _ = extract(empty_batches())

    chunk_nodes = [n for n in csg.nodes if n.type == NodeType.CHUNK]
    assert chunk_nodes and all(n.props["embedding"] == [0.1, 0.2, 0.3]
                               for n in chunk_nodes)
    part_of = [e for e in csg.edges if e.type == EdgeType.PART_OF]
    assert len(part_of) == len(chunk_nodes)


def test_regex_pass_finds_tags_without_llm():
    csg, _ = extract(empty_batches())

    surfaces = {n.surface_form for n in csg.nodes}
    assert {"P-101A", "P-101B", "T-101", "E-204", "PI-102", "FT-103"} <= surfaces

    pi102 = next(n for n in csg.nodes if n.surface_form == "PI-102")
    assert pi102.type == NodeType.INSTRUMENT          # prefix says instrument
    p101a = next(n for n in csg.nodes if n.surface_form == "P-101A")
    assert p101a.type == NodeType.EQUIPMENT

    mention = next(e for e in csg.edges if e.type == EdgeType.MENTIONED_IN
                   and e.src == "P-101A")
    start, end = mention.provenance.span
    assert SOP[start:end] == "P-101A"                 # span survives chunking


def test_llm_findings_become_edges():
    responses = empty_batches()
    responses[0] = BatchFindings(
        failures=[FailureFinding(chunk_index=0, equipment_tag="P-101A",
                                 failure_mode="seal leak",
                                 cause="cavitation", confidence=0.9)],
        procedures=[ProcedureFinding(chunk_index=1, equipment_tag="P-101B",
                                     procedure_name="Mechanical Seal Replacement")],
    )
    csg, _ = extract(responses)

    failure = next(e for e in csg.edges if e.type == EdgeType.HAS_FAILURE)
    assert failure.src == "P-101A" and failure.dst == "SEAL-LEAK"
    assert failure.provenance.confidence == 0.9
    assert failure.props["cause"] == "cavitation"

    fixed = next(e for e in csg.edges if e.type == EdgeType.FIXED_BY)
    assert fixed.src == "P-101B"
    assert fixed.dst == "Mechanical Seal Replacement"


def test_hallucinated_tags_are_dropped():
    responses = empty_batches()
    responses[0] = BatchFindings(
        failures=[FailureFinding(chunk_index=0, equipment_tag="the main pump",
                                 failure_mode="leak")])
    csg, _ = extract(responses)

    assert not [e for e in csg.edges if e.type == EdgeType.HAS_FAILURE]
    assert "the main pump" not in {n.surface_form for n in csg.nodes}


def test_empty_document_rejected():
    extractor = TextExtractor(FakeLLM(), FakeEmbedder())
    with pytest.raises(ValueError, match="no extractable text"):
        asyncio.run(extractor.extract("d", "h", "empty.md", "   \n"))
