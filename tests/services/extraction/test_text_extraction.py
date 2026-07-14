import asyncio

import pytest

from plantmind_core.config import get_settings
from plantmind_core.schemas import EdgeType, NodeType
from extraction.text.chunker import SectionChunker
from extraction.text.extractor import (
    BatchFindings, FailureFinding, ProcedureFinding, TextExtractor,
)
from conftest import SAMPLES, FakeEmbedder, FakeLLM

SOP = (SAMPLES / "sop_pump_seal_replacement.md").read_text(encoding="utf-8")


class RecordingEmbedder(FakeEmbedder):
    def __init__(self):
        self.inputs = []

    async def embed(self, texts):
        self.inputs.extend(texts)
        return await super().embed(texts)


def all_chunks(sections):
    return [c for s in sections for c in s.chunks]


def test_chunker_builds_section_tree_with_exact_offsets():
    sections = SectionChunker().split(SOP)

    titles = {s.title for s in sections}
    assert "1. Safety prerequisites" in titles
    assert "4. Pre-start checks" in titles

    chunks = all_chunks(sections)
    assert chunks
    for c in chunks:
        assert SOP[c.start:c.end] == c.text        # exact, not just stripped
    indices = [c.index for c in chunks]
    assert indices == list(range(len(chunks)))     # global, gapless


def n_batches():
    n = len(all_chunks(SectionChunker().split(SOP)))
    return -(-n // get_settings().extraction_batch_size)


def empty_batches():
    return [BatchFindings() for _ in range(n_batches())]


def extract(llm_responses, embedder=None):
    llm = FakeLLM(*llm_responses)
    extractor = TextExtractor(llm, embedder or FakeEmbedder())
    csg = asyncio.run(extractor.extract("doc-sop", "hash-sop", "sop.md", SOP))
    return csg, llm


def test_parent_child_structure_in_graph():
    csg, _ = extract(empty_batches())

    section_nodes = [n for n in csg.nodes if n.type == NodeType.SECTION]
    chunk_nodes = [n for n in csg.nodes if n.type == NodeType.CHUNK]
    assert section_nodes and chunk_nodes

    part_of = [(e.src, e.dst) for e in csg.edges if e.type == EdgeType.PART_OF]
    for s in section_nodes:                        # every section hangs off the doc
        assert (s.surface_form, "doc-sop") in part_of
    for c in chunk_nodes:                          # every chunk hangs off a section
        parents = [dst for src, dst in part_of if src == c.surface_form]
        assert len(parents) == 1 and "#sec" in parents[0]

    prestart = next(n for n in section_nodes
                    if n.props["title"] == "4. Pre-start checks")
    assert "0.8 barg" in prestart.props["text"]    # parent carries full context


def test_embeddings_use_contextual_enrichment():
    embedder = RecordingEmbedder()
    csg, _ = extract(empty_batches(), embedder)

    assert embedder.inputs
    assert all(i.startswith("From sop.md, section ") for i in embedder.inputs)

    chunk = next(n for n in csg.nodes if n.type == NodeType.CHUNK)
    assert not chunk.props["text"].startswith("From sop.md")   # raw text stays raw
    assert chunk.props["context"].startswith("From sop.md, section ")


def test_prompt_carries_tag_list_and_negation_rules():
    _, llm = extract(empty_batches())

    prompt = llm.calls[0][1][0]["content"]
    assert "P-101A" in prompt and "PI-102" in prompt          # coref tag list
    assert "no leakage observed" in prompt                    # negation trap
    assert "inspect for cavitation" in prompt                 # instruction trap
    assert "Never report a tag" in prompt                     # coref guard


def test_regex_pass_finds_tags_without_llm():
    csg, _ = extract(empty_batches())

    surfaces = {n.surface_form for n in csg.nodes}
    assert {"P-101A", "P-101B", "T-101", "E-204", "PI-102", "FT-103"} <= surfaces

    pi102 = next(n for n in csg.nodes if n.surface_form == "PI-102")
    assert pi102.type == NodeType.INSTRUMENT
    mention = next(e for e in csg.edges if e.type == EdgeType.MENTIONED_IN
                   and e.src == "P-101A")
    start, end = mention.provenance.span
    assert SOP[start:end] == "P-101A"


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
