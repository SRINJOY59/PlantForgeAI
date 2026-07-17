"""The investigator wires an LLM tool-agent to the graph reader. Here the
LLM is scripted to call one tool then answer, so we verify the whole path
(tools bound to the reader, trace -> citations, alert shape) offline."""

import asyncio
from types import SimpleNamespace

from agents.usecases.failure_rca import InvestigatorAgent
from agents.watchers import Trigger
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


def reader_with_history():
    r = FakeAgentReader()
    r.failures["equip:P-101A"] = [
        {"tag": "P-101A", "mode": "SEAL-LEAK", "count": 3,
         "causes": ["cavitation"], "docs": ["work_orders.csv", "sop.md"]}]
    return r


def test_investigator_uses_tools_and_builds_alert():
    reader = reader_with_history()
    trigger = Trigger(tag="P-101B", mode="SEAL-LEAK", count=1, family="P-101",
                      siblings=[{"tag": "P-101A", "count": 3}], graph_version=9)

    # agent calls get_failure_history on the sibling, then recommends
    llm = ScriptedLLM(
        msg(tool_calls=[tool_call("get_failure_history", '{"tag": "P-101A"}')]),
        msg(content="P-101A had 3 seal leaks from cavitation; check PI-102 "
                    ">= 0.8 barg and the suction strainer before restart."))

    alert = asyncio.run(InvestigatorAgent(reader, llm=llm).investigate(trigger))

    assert alert.kind == "failure_pattern"
    assert alert.equipment == "P-101B"
    assert "cavitation" in alert.body
    assert alert.fingerprint == "failure:P-101B:SEAL-LEAK:1"
    assert alert.graph_version == 9
    # citations harvested from the tool results the agent actually pulled
    assert {c.doc_id for c in alert.citations} == {"work_orders.csv", "sop.md"}


def test_severity_critical_when_recurring_and_siblings():
    reader = reader_with_history()
    trigger = Trigger(tag="P-101B", mode="SEAL-LEAK", count=2, family="P-101",
                      siblings=[{"tag": "P-101A", "count": 3}], graph_version=1)
    llm = ScriptedLLM(msg(content="advice for P-101B"))

    alert = asyncio.run(InvestigatorAgent(reader, llm=llm).investigate(trigger))
    assert alert.severity == "critical"
    assert alert.verified is True


def test_ungrounded_agent_output_is_flagged_and_capped():
    reader = reader_with_history()
    trigger = Trigger(tag="P-101B", mode="SEAL-LEAK", count=2, family="P-101",
                      siblings=[{"tag": "P-101A", "count": 3}], graph_version=1)
    # agent hallucinates a tag it never gathered evidence for
    llm = ScriptedLLM(msg(content="Root cause is shared with X-777, replace it."))

    alert = asyncio.run(InvestigatorAgent(reader, llm=llm).investigate(trigger))

    assert alert.verified is False
    assert "X-777" in alert.unverified_claims
    assert "UNVERIFIED" in alert.body
    assert alert.severity == "warning"          # trust capped despite pattern
