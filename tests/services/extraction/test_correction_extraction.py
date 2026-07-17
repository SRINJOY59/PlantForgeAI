"""The correction lane is the only way a person writes into the graph, so what
matters is the tier: a human fact must arrive marked HUMAN at full confidence,
and the record of what was wrong must survive even when the fix cannot be
parsed."""

import pytest

from plantmind_core import corrections
from plantmind_core.schemas import EdgeType, NodeType, Source

from extraction.correction.extractor import (CorrectionExtractor,
                                             CorrectionFacts, ExtractedEdge,
                                             ExtractedNode)

QUESTION = "How many seal failures has P-101A had?"
ANSWER = "P-101A has had 3 seal failures, all caused by cavitation [doc:sop-1]."
FIX = ("Only 2 were cavitation. The January one was misalignment after the "
       "coupling change.")


class FakeLLM:
    def __init__(self, facts=None, fail=False):
        self.facts = facts if facts is not None else CorrectionFacts(
            nodes=[ExtractedNode(type="Equipment", surface_form="P-101A"),
                   ExtractedNode(type="FailureMode", surface_form="MISALIGNMENT")],
            edges=[ExtractedEdge(type="HAS_FAILURE", src="P-101A",
                                 dst="MISALIGNMENT",
                                 note="January, after the coupling change")])
        self.fail = fail
        self.prompts = []

    async def structured(self, messages, schema, tier=None, max_tokens=None):
        self.prompts.append(messages[0]["content"])
        if self.fail:
            raise RuntimeError("provider exploded")
        return self.facts


async def extract(llm=None, wrong_docs=("sop-1",)):
    return await CorrectionExtractor(llm or FakeLLM()).extract(
        doc_id="corr-1", content_hash="h1", question=QUESTION, answer=ANSWER,
        correction=FIX, author="eng@plant.com", wrong_doc_ids=list(wrong_docs))


# -- the tier -----------------------------------------------------------------
async def test_every_edge_is_marked_human():
    csg = await extract()
    assert csg.edges
    assert all(e.provenance.source is Source.HUMAN for e in csg.edges)


async def test_a_human_fact_carries_full_confidence():
    # the pruner multiplies flow by edge confidence, so this is what makes a
    # human fact outrank a hedged extraction with no special case downstream
    csg = await extract()
    assert all(e.provenance.confidence == 1.0 for e in csg.edges)
    assert all(n.confidence == 1.0 for n in csg.nodes)


async def test_the_author_rides_on_every_edge():
    csg = await extract()
    assert all(e.props["corrected_by"] == "eng@plant.com" for e in csg.edges)


# -- the fact -----------------------------------------------------------------
async def test_the_corrected_fact_becomes_nodes_and_edges():
    csg = await extract()
    assert {n.surface_form for n in csg.nodes} >= {"P-101A", "MISALIGNMENT"}
    fixed = [e for e in csg.edges if e.type is EdgeType.HAS_FAILURE]
    assert len(fixed) == 1
    assert (fixed[0].src, fixed[0].dst) == ("P-101A", "MISALIGNMENT")
    assert "coupling" in fixed[0].props["note"]


async def test_the_model_is_shown_the_question_answer_and_correction():
    llm = FakeLLM()
    await extract(llm)
    prompt = llm.prompts[0]
    assert QUESTION in prompt and ANSWER in prompt and FIX in prompt


async def test_an_edge_type_we_do_not_model_is_dropped_not_guessed():
    llm = FakeLLM(CorrectionFacts(
        nodes=[ExtractedNode(type="Equipment", surface_form="P-101A")],
        edges=[ExtractedEdge(type="SMELLS_LIKE", src="P-101A", dst="X")]))
    csg = await extract(llm, wrong_docs=())
    assert csg.edges == []


async def test_an_unknown_node_type_falls_back_to_equipment():
    llm = FakeLLM(CorrectionFacts(
        nodes=[ExtractedNode(type="Gizmo", surface_form="P-101A")], edges=[]))
    csg = await extract(llm, wrong_docs=())
    assert csg.nodes[0].type is NodeType.EQUIPMENT


# -- the graph of mistakes ----------------------------------------------------
async def test_every_document_the_bad_answer_cited_points_at_the_correction():
    csg = await CorrectionExtractor(FakeLLM()).extract(
        doc_id="corr-1", content_hash="h1", question=QUESTION, answer=ANSWER,
        correction=FIX, author="eng@plant.com",
        wrong_doc_ids=["sop-1", "wo-2"])
    corrected = [e for e in csg.edges if e.type is EdgeType.CORRECTED_BY]
    assert {(e.src, e.dst) for e in corrected} == {("sop-1", "corr-1"),
                                                   ("wo-2", "corr-1")}


async def test_the_correction_itself_becomes_a_document_node():
    csg = await extract()
    doc = next(n for n in csg.nodes if n.surface_form == "corr-1")
    assert doc.type is NodeType.DOCUMENT
    assert doc.props["kind"] == "correction"
    assert doc.props["author"] == "eng@plant.com"


async def test_a_repeated_cited_doc_only_gets_one_edge():
    csg = await CorrectionExtractor(FakeLLM()).extract(
        doc_id="corr-1", content_hash="h1", question=QUESTION, answer=ANSWER,
        correction=FIX, author="e", wrong_doc_ids=["sop-1", "sop-1"])
    corrected = [e for e in csg.edges if e.type is EdgeType.CORRECTED_BY]
    assert len(corrected) == 1


async def test_the_mistake_record_survives_a_failed_extraction():
    # we could not parse the fix, but we still know which documents an
    # engineer challenged - that is worth keeping on its own
    csg = await extract(FakeLLM(fail=True))
    corrected = [e for e in csg.edges if e.type is EdgeType.CORRECTED_BY]
    assert len(corrected) == 1
    assert corrected[0].provenance.source is Source.HUMAN


async def test_an_answer_that_cited_nothing_leaves_no_mistake_record():
    csg = await extract(wrong_docs=())
    assert not [e for e in csg.edges if e.type is EdgeType.CORRECTED_BY]


# -- the document format ------------------------------------------------------
def test_a_correction_round_trips_through_its_document():
    original = corrections.Correction(
        question=QUESTION, answer=ANSWER, correction=FIX,
        author="eng@plant.com", date="2026-07-17",
        cited_docs=["sop-1", "wo-2"])
    back = corrections.parse(corrections.render(original).decode())
    assert back == original


def test_a_multi_line_correction_survives_the_round_trip():
    # an engineer will write lists and paragraphs; only a heading ends a section
    body = "Two things:\n\n- the January one was misalignment\n- WO-2233 is misfiled\n\nCheck the coupling."
    original = corrections.Correction(question="q", answer="a", correction=body,
                                      author="e", date="2026-07-17",
                                      cited_docs=[])
    assert corrections.parse(corrections.render(original).decode()).correction == body


def test_a_correction_filename_is_recognisable_as_one():
    assert corrections.filename("abc123").endswith(corrections.SUFFIX)
