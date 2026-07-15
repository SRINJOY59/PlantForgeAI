"""A general tool-calling agent loop. Give it tools (a name, a description,
a params schema, and a function); it lets the model call them iteratively
until the model answers or the step budget runs out. Provider-agnostic via
the OpenAI tool-calling format."""

import json
from dataclasses import dataclass
from typing import Callable

from plantmind_core.llm.client import Tier, get_llm
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
                return AgentResult(answer=msg.content or "", steps=step,
                                   trace=trace)

            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [_call_dict(c) for c in calls]})
            for call in calls:
                result = self._dispatch(call, trace)
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps(result, default=str)})

        # budget exhausted: force a final answer without tools
        messages.append({"role": "user", "content":
                         "Give your best final answer now, no more tools."})
        answer = await self._llm.complete(messages, tier=self._tier)
        return AgentResult(answer=answer, steps=self._max_steps, trace=trace)

    def _dispatch(self, call, trace) -> dict:
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"unknown tool {name}"}
        try:
            result = tool.fn(**args)
        except Exception as e:
            log.warning("tool call failed", tool=name, error=str(e)[:200])
            result = {"error": str(e)[:200]}
        trace.append((name, args, result))
        return result


def _call_dict(call) -> dict:
    return {"id": call.id, "type": "function",
            "function": {"name": call.function.name,
                         "arguments": call.function.arguments}}
