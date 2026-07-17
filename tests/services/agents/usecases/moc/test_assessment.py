"""The structured fields are the part a reviewer might paste into a statutory
form, so they must be facts about the graph rather than claims about it. These
tests exist to keep them that way."""

from types import SimpleNamespace

from plantmind_core.schemas import ChangeProposal

from agents.usecases.moc import assessment

PROPOSAL = ChangeProposal(tag="P-101A", summary="replace mechanical seal",
                          proposed_by="eng@plant.com")


def reasoned(answer="fine", trace=None, verified=True, ungrounded=None,
             docs=None):
    return SimpleNamespace(
        answer=answer, trace=trace or [], docs=docs or [],
        grounding=SimpleNamespace(verified=verified,
                                  ungrounded_tags=ungrounded or []))


def test_lists_come_from_tool_results_not_from_the_prose():
    # the model claims a clause nobody returned; it must not reach the field a
    # reviewer would copy
    trace = [
        ("get_governing_clauses", {}, [{"clause": "OISD-STD-119"}]),
        ("get_connected_equipment", {}, [{"tag": "PI-102"}]),
    ]
    out = assessment.build(
        PROPOSAL, reasoned(answer="Also governed by OISD-STD-999.", trace=trace))

    assert out.governing_clauses == ["OISD-STD-119"]
    assert "OISD-STD-999" not in out.governing_clauses
    assert out.affected_equipment == ["PI-102"]


def test_documents_to_revise_are_harvested():
    trace = [("get_documents_mentioning", {},
              [{"document": "sop-101.md"}, {"document": "wo-2231"}])]
    out = assessment.build(PROPOSAL, reasoned(trace=trace))
    assert out.documents_to_revise == ["sop-101.md", "wo-2231"]


def test_documents_to_revise_are_names_a_person_can_act_on():
    # the reader coalesces filename over surface_form; this pins the contract
    # that harvesting reads the named field, because "revise 6d6d71a9e053a1bd"
    # is not a task anyone can do
    trace = [("get_documents_mentioning", {}, [
        {"document": "sop_pump_seal_replacement.md", "label": "Document",
         "doc_id": "6d6d71a9e053a1bd"},
        {"document": "WO-2214", "label": "WorkOrder", "doc_id": "wo-doc"}])]
    out = assessment.build(PROPOSAL, reasoned(trace=trace))

    assert out.documents_to_revise == ["WO-2214", "sop_pump_seal_replacement.md"]
    assert not any(len(d) == 16 and d.isalnum() and d.islower()
                   for d in out.documents_to_revise)


def test_a_tool_never_called_leaves_an_honest_empty_list():
    # empty means nobody looked, which serves a reviewer better than prose
    # asserting the change touches nothing
    out = assessment.build(PROPOSAL, reasoned(trace=[]))
    assert out.documents_to_revise == []
    assert out.governing_clauses == []
    assert out.affected_equipment == []


def test_duplicates_across_tool_calls_collapse():
    trace = [
        ("get_connected_equipment", {}, [{"tag": "PI-102"}, {"tag": "V-203"}]),
        ("get_connected_equipment", {}, [{"tag": "PI-102"}]),
    ]
    out = assessment.build(PROPOSAL, reasoned(trace=trace))
    assert out.affected_equipment == ["PI-102", "V-203"]


def test_ungrounded_prose_is_marked_on_the_body():
    out = assessment.build(
        PROPOSAL, reasoned(answer="Replace X-777 too.", verified=False,
                           ungrounded=["X-777"]))
    assert out.verified is False
    assert "UNVERIFIED" in out.body
    assert out.unverified_claims == ["X-777"]


def test_no_verdict_field_exists():
    # approving a change is a legal act by a competent person. If this ever
    # grows a verdict, that decision should be made deliberately, not by
    # somebody adding a field
    out = assessment.build(PROPOSAL, reasoned())
    assert not hasattr(out, "verdict")
    assert not hasattr(out, "approved")


def test_corrected_facts_are_visible_to_the_caller():
    # the shape the real reader returns: the failure is sourced from documents
    # and the correction is joined in through them, never carried on the edge
    trace = [("get_failure_history", {}, [
        {"tag": "P-101A", "mode": "SEAL-LEAK", "count": 3,
         "sources": ["document"], "corrected_by": ["eng@plant.com"],
         "corrections": ["January was misalignment, not cavitation."]}])]
    found = assessment.corrected_facts(trace)
    assert len(found) == 1
    assert found[0]["corrected_by"] == ["eng@plant.com"]


def test_uncorrected_history_reports_nothing():
    trace = [("get_failure_history", {}, [
        {"tag": "P-101A", "mode": "SEAL-LEAK", "count": 3,
         "sources": ["document"], "corrected_by": [], "corrections": []}])]
    assert assessment.corrected_facts(trace) == []
