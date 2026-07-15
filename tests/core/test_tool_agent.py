"""ToolAgent drives a tool-calling loop. These fakes emulate the provider's
message shape (tool_calls, then a final content message)."""

from types import SimpleNamespace

import pytest

from plantmind_core.llm.agent import Tool, ToolAgent


def tool_call(call_id, name, arguments):
    return SimpleNamespace(id=call_id, type="function",
                           function=SimpleNamespace(name=name,
                                                    arguments=arguments))


def msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


class ScriptedLLM:
    """Yields queued assistant messages; records tool-result messages seen."""

    def __init__(self, *messages):
        self.queue = list(messages)
        self.seen = []

    async def chat_with_tools(self, messages, tools, tier=None, max_tokens=2048):
        self.seen = messages
        return self.queue.pop(0)

    async def complete(self, messages, tier=None, max_tokens=2048):
        return "forced final answer"


def calc_tool():
    calls = []

    def add(a, b):
        calls.append((a, b))
        return {"sum": a + b}

    return Tool("add", "add two numbers",
                {"type": "object", "properties": {"a": {"type": "number"},
                                                  "b": {"type": "number"}},
                 "required": ["a", "b"]}, add), calls


async def test_agent_calls_tool_then_answers():
    tool, calls = calc_tool()
    llm = ScriptedLLM(
        msg(tool_calls=[tool_call("c1", "add", '{"a": 2, "b": 3}')]),
        msg(content="the sum is 5"))

    agent = ToolAgent([tool], llm=llm)
    result = await agent.run("system", "add 2 and 3")

    assert result.answer == "the sum is 5"
    assert calls == [(2, 3)]
    assert result.trace == [("add", {"a": 2, "b": 3}, {"sum": 5})]
    assert result.steps == 1


async def test_agent_answers_without_tools():
    tool, _ = calc_tool()
    llm = ScriptedLLM(msg(content="no tool needed"))

    result = await ToolAgent([tool], llm=llm).run("s", "hi")
    assert result.answer == "no tool needed"
    assert result.trace == []


async def test_unknown_tool_returns_error_not_crash():
    tool, _ = calc_tool()
    llm = ScriptedLLM(
        msg(tool_calls=[tool_call("c1", "divide", '{"a": 1, "b": 0}')]),
        msg(content="handled"))

    result = await ToolAgent([tool], llm=llm).run("s", "t")
    assert result.answer == "handled"
    assert result.trace[0][0] == "divide"
    assert "error" in result.trace[0][2]


async def test_tool_exception_is_captured():
    def boom(**_):
        raise RuntimeError("db down")
    tool = Tool("boom", "boom", {"type": "object", "properties": {}}, boom)
    llm = ScriptedLLM(
        msg(tool_calls=[tool_call("c1", "boom", "{}")]),
        msg(content="recovered"))

    result = await ToolAgent([tool], llm=llm).run("s", "t")
    assert "error" in result.trace[0][2]


async def test_step_budget_forces_final_answer():
    tool, _ = calc_tool()
    # always asks for a tool, never answers -> budget exhausts
    looping = [msg(tool_calls=[tool_call(f"c{i}", "add", '{"a":1,"b":1}')])
               for i in range(6)]
    llm = ScriptedLLM(*looping)

    result = await ToolAgent([tool], max_steps=3, llm=llm).run("s", "t")
    assert result.answer == "forced final answer"
    assert result.steps == 3
