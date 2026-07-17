"""Impact assessment for a change nobody has made yet.

Same engine as the failure investigation - graph tools, a system prompt, a
grounding check. The difference is the trigger: a person proposed something,
rather than a delta landing. That is the only difference, and it is the point.
Everything the plant already knows about an asset is exactly what you need to
know before you change it.
"""

from plantmind_core.schemas import ChangeProposal, ImpactAssessment
from plantmind_core.telemetry import get_logger

from agents import tools
from agents.usecases.base import GraphAgent
from agents.usecases.moc import assessment, prompts

log = get_logger("agents.usecases.moc")


class ChangeImpact(GraphAgent):
    system = prompts.SYSTEM

    def tools(self) -> list:
        r = self._reader
        return [tools.connected_equipment(r), tools.failure_history(r),
                tools.governing_clauses(r), tools.documents_mentioning(r),
                tools.fix_procedures(r)]

    async def assess(self, proposal: ChangeProposal,
                     graph_version: int = 0) -> ImpactAssessment:
        reasoned = await self.reason(prompts.task(proposal), {proposal.tag})
        return self._finish(proposal, reasoned, graph_version)

    async def assess_stream(self, proposal: ChangeProposal,
                            graph_version: int = 0):
        """assess(), streamed. Yields ('step', tool_name) as the agent gathers
        evidence, ('token', delta) as the assessment is written, and finally
        ('done', ImpactAssessment) - the structured envelope, which can only be
        harvested once the whole answer exists."""
        async for kind, payload in self.reason_stream(prompts.task(proposal),
                                                      {proposal.tag}):
            if kind == "reasoned":
                yield "done", self._finish(proposal, payload, graph_version)
            else:
                yield kind, payload

    def _finish(self, proposal, reasoned, graph_version) -> ImpactAssessment:
        names = self._reader.document_names(reasoned.docs)
        result = assessment.build(proposal, reasoned, graph_version, names)
        log.info("change assessed", tag=proposal.tag,
                 tools_used=len(reasoned.trace),
                 affected=len(result.affected_equipment),
                 to_revise=len(result.documents_to_revise),
                 corrected_facts=len(assessment.corrected_facts(reasoned.trace)),
                 verified=result.verified)
        return result
