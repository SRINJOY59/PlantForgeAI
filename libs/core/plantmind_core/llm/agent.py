"""A general tool-calling agent loop. Give it tools (a name, a description,
a params schema, and a function); it lets the model call them iteratively
until the model answers or the step budget runs out. Provider-agnostic via
the OpenAI tool-calling format."""

import asyncio
import json
from dataclasses import dataclass
from typing import Callable

from plantmind_core.llm.client import Tier, get_llm, sanitize_text
from plantmind_core.telemetry import get_logger

log = get_logger("llm.agent")


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict          # JSON schema for the arguments
    fn: Callable              # fn(**args) -> anything json-serialisable

    def spec(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.parameters}}


@dataclass
class AgentResult:
    answer: str
    steps: int
    trace: list               # [(tool_name, args, result)] for auditability


class ToolAgent:
    def __init__(self, tools, tier=Tier.MID, max_steps=6, llm=None):
        self._tools = {t.name: t for t in tools}
        self._specs = [t.spec() for t in tools]
        self._tier = tier
        self._max_steps = max_steps
        self._llm = llm or get_llm()

    async def run(self, system: str, task: str) -> AgentResult:
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": task}]
        trace = []

        for step in range(self._max_steps):
            msg = await self._llm.chat_with_tools(
                messages, self._specs, tier=self._tier)
            calls = getattr(msg, "tool_calls", None)

            if not calls:
                # sanitize, not msg.content: when the provider fails to parse a
                # DeepSeek-style tool call it lands here as literal markup with
                # no tool_calls attached, which is exactly the path that put
                # "<｜｜DSML｜｜invoke name=..." into a work permit
                return AgentResult(answer=sanitize_text(msg.content or ""),
                                   steps=step, trace=trace)

            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [_call_dict(c) for c in calls]})
            for call in calls:
                result = await self._dispatch(call, trace)
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps(result, default=str)})

        # budget exhausted: force a final answer without tools
        messages.append({"role": "user", "content":
                         "Give your best final answer now, no more tools."})
        answer = await self._llm.complete(messages, tier=self._tier)
        return AgentResult(answer=answer, steps=self._max_steps, trace=trace)

    async def stream_run(self, system: str, task: str):
        """The same loop as run(), but as a stream. Yields ('step', tool_name)
        as the agent gathers evidence, then ('token', delta) for the final
        synthesis, then ('result', AgentResult) once it is whole.

        The tokens are real, not a replay of a finished string: the tool loop
        runs to the point the model stops asking for tools, and the closing
        synthesis is then generated with stream(). That final call is the one
        extra generation streaming costs - honest tokens beat a fake reveal of
        text we already had.
        """
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": task}]
        trace = []
        used = 0

        for step in range(self._max_steps):
            msg = await self._llm.chat_with_tools(
                messages, self._specs, tier=self._tier)
            calls = getattr(msg, "tool_calls", None)
            used = step
            if not calls:
                break                      # the model is ready to answer
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [_call_dict(c) for c in calls]})
            for call in calls:
                result = await self._dispatch(call, trace)
                yield "step", call.function.name
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps(result, default=str)})

        parts = []
        async for delta in self._llm.stream(messages, tier=self._tier):
            parts.append(delta)
            yield "token", delta
        # the deltas already reached the UI, but the artifact built from this
        # is what gets stored, cited and signed - so it is sanitized here
        yield "result", AgentResult(answer=sanitize_text("".join(parts)),
                                    steps=used, trace=trace)

    async def _dispatch(self, call, trace) -> dict:
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        tool = self._tools.get(name)
        if tool is None:
            result = {"error": f"unknown tool {name}"}
        else:
            try:
                # tool fns are synchronous graph reads on the sync Neo4j driver;
                # run them off the event loop so one agent's tool calls don't
                # block every other request the process is serving
                result = await asyncio.to_thread(tool.fn, **args)
            except Exception as e:
                log.warning("tool call failed", tool=name, error=str(e)[:200])
                result = {"error": str(e)[:200]}
        trace.append((name, args, result))
        return result


def _call_dict(call) -> dict:
    return {"id": call.id, "type": "function",
            "function": {"name": call.function.name,
                         "arguments": call.function.arguments}}
