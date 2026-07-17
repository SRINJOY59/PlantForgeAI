"""Same offline shape as the failure investigation test: the LLM is scripted so
the whole path (tools bound to the reader, trace -> assessment, grounding) runs
without a network."""

import asyncio
from types import SimpleNamespace

from plantmind_core.schemas import ChangeProposal

from agents.usecases.moc import ChangeImpact
from conftest import FakeAgentReader


def tool_call(name, args):
    return SimpleNamespace(id="c1", type="function",
                           function=SimpleNamespace(name=name, arguments=args))


def msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


class ScriptedLLM:
    def __init__(self, *messages):
        self.queue = list(messages)

    async def chat_with_tools(self, messages, tools, tier=None, max_tokens=2048):
        return self.queue.pop(0)

    async def complete(self, messages, tier=None, max_tokens=2048):
        return "final"


PROPOSAL = ChangeProposal(tag="P-101A", summary="replace mechanical seal",
                          proposed_by="eng@plant.com")


def corrected_reader():
    """P-101A's seal history in the shape the real reader returns it.

    Mirrors the live graph deliberately: the failure edges are all sourced from
    documents, and the correction is found by joining through those documents -
    it is never on the failure edge itself. An earlier version of this fake put
    corrected_by on the edge, and passed while the real query returned nothing.
    """
    r = FakeAgentReader()
    r.failures["equip:P-101A"] = [
        {"tag": "P-101A", "mode": "SEAL-LEAK", "count": 3,
         "causes": ["cavitation"],
         "docs": ["sop-101.md", "corr-9.md"],
         "sources": ["document"],
         "corrected_by": ["eng@plant.com"],
         "corrections": ["Only two were cavitation. January was misalignment "
                         "after the coupling change."],
         "correction_ids": ["doc:corr-9"]}]
    r.clauses["equip:P-101A"] = [
        {"clause": "OISD-STD-119", "revision": "2019",
         "inspection_type": "Condition monitoring", "next_due": "2025-09-15",
         "doc_id": "ins-1"}]
    r.mentions["equip:P-101A"] = [{"document": "sop-101.md", "label": "Document",
                                   "kind": None, "doc_id": "sop-101.md"}]
    r.connections["P-101A"] = [{"tag": "PI-102", "label": "Instrument"}]
    return r


def test_assessment_is_built_from_the_tools_the_agent_pulled():
    llm = ScriptedLLM(
        msg(tool_calls=[tool_call("get_governing_clauses", '{"tag": "P-101A"}')]),
        msg(tool_calls=[tool_call("get_documents_mentioning", '{"tag": "P-101A"}')]),
        msg(tool_calls=[tool_call("get_connected_equipment", '{"tag": "P-101A"}')]),
        msg(content="P-101A is governed by OISD-STD-119; sop-101.md must be "
                    "revised. PI-102 is affected."))

    out = asyncio.run(ChangeImpact(corrected_reader(), llm=llm)
                      .assess(PROPOSAL, graph_version=12))

    assert out.proposal.tag == "P-101A"
    assert out.governing_clauses == ["OISD-STD-119"]
    assert out.documents_to_revise == ["sop-101.md"]
    assert out.affected_equipment == ["PI-102"]
    assert out.graph_version == 12
    assert out.verified is True


def test_naming_equipment_it_never_looked_up_is_not_verified():
    """The failure my own first draft of the test above hit: the model named
    PI-102 without pulling the connection. Real, and exactly what should
    happen - an assessment is only as good as what it actually checked."""
    llm = ScriptedLLM(
        msg(tool_calls=[tool_call("get_governing_clauses", '{"tag": "P-101A"}')]),
        msg(content="PI-102 is affected."))

    out = asyncio.run(ChangeImpact(corrected_reader(), llm=llm).assess(PROPOSAL))

    assert out.verified is False
    assert "PI-102" in out.unverified_claims
    assert out.affected_equipment == []


def test_the_correction_reaches_the_agent_with_the_failure_it_corrects():
    """The feature's whole premise. If the correction is not in front of the
    model when it reasons about the seal, it recommends the wrong change."""
    llm = ScriptedLLM(
        msg(tool_calls=[tool_call("get_failure_history", '{"tag": "P-101A"}')]),
        msg(content="Two of three were cavitation; January was misalignment "
                    "after the coupling change, per the correction. A new seal "
                    "does not address that."))

    agent = ChangeImpact(corrected_reader(), llm=llm)
    out = asyncio.run(agent.assess(PROPOSAL))

    assert "misalignment" in out.body
    assert out.verified is True
    # the corrected doc is cited, so a reader can check the claim
    assert "corr-9.md" in {c.doc_id for c in out.citations}


def test_invented_clause_is_caught_and_the_assessment_marked():
    llm = ScriptedLLM(msg(content="Also affects X-777 under a separate clause."))

    out = asyncio.run(ChangeImpact(corrected_reader(), llm=llm).assess(PROPOSAL))

    assert out.verified is False
    assert "X-777" in out.unverified_claims
    assert "UNVERIFIED" in out.body
    # and it never reached the structured field
    assert "X-777" not in out.affected_equipment
