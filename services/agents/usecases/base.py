"""What the tool-using use-cases share, and nothing more.

The shared part is one step: reason over graph tools, then check the answer
against the evidence the tools returned. That step is identical whether a delta
triggered it or a person did.

What is deliberately NOT shared is the interface. A failure investigation owes
its caller an Alert and a change assessment owes one an ImpactAssessment; those
are not the same thing, and a uniform run(subject) -> artifact would force both
through a shape that fits neither. Subclasses keep their own honest signature
and build their own artifact. Compliance and the standards watch live alongside
these without inheriting anything here at all - one has no LLM, the other has
no graph tools, and pretending otherwise would buy nothing.
"""

from dataclasses import dataclass

from plantmind_core.llm import Tier, ToolAgent

from agents.verifier import Grounding, check_grounding, docs_from_trace

MAX_STEPS = 6


@dataclass
class Reasoned:
    """What the engine produced, before a use-case shapes it into an artifact.
    Internal to the agents service - it never crosses a wire, so it lives here
    rather than in the shared contracts."""
    answer: str
    trace: list
    docs: list
    grounding: Grounding


class GraphAgent:
    """A system prompt, a tool set over the graph, and a grounded result."""

    system: str = ""

    def __init__(self, reader, llm=None):
        self._reader = reader
        self._llm = llm

    def tools(self) -> list:
        raise NotImplementedError

    async def reason(self, task: str, given: set) -> Reasoned:
        agent = ToolAgent(self.tools(), tier=Tier.MID, max_steps=MAX_STEPS,
                          llm=self._llm)
        result = await agent.run(self.system, task)
        return self._reasoned(result, given)

    async def reason_stream(self, task: str, given: set):
        """reason(), streamed. Yields ('step', tool_name) and ('token', delta)
        as they happen, then ('reasoned', Reasoned) once grounding can be
        checked - which needs the whole answer, so it can only come last."""
        agent = ToolAgent(self.tools(), tier=Tier.MID, max_steps=MAX_STEPS,
                          llm=self._llm)
        async for kind, payload in agent.stream_run(self.system, task):
            if kind == "result":
                yield "reasoned", self._reasoned(payload, given)
            else:
                yield kind, payload

    def _reasoned(self, result, given: set) -> Reasoned:
        grounding = check_grounding(result.answer, result.trace, given)
        return Reasoned(answer=result.answer, trace=result.trace,
                        docs=docs_from_trace(result.trace), grounding=grounding)
