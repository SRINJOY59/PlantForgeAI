"""Impact assessment for a change nobody has made yet.

Same engine as the failure investigation - graph tools, a system prompt, a
grounding check. The difference is the trigger: a person proposed something,
rather than a delta landing. That is the only difference, and it is the point.
Everything the plant already knows about an asset is exactly what you need to
know before you change it.

When wired with an AgentBroker the assessment also:
  - Appends outstanding compliance flags for the target equipment to the
    governing_clauses list so the reviewer sees the full regulatory picture.
"""

import asyncio
from typing import TYPE_CHECKING

from plantmind_core.schemas import ChangeProposal, ImpactAssessment
from plantmind_core.telemetry import get_logger

from agents import tools
from agents.usecases.base import GraphAgent
from agents.usecases.moc import assessment, prompts

if TYPE_CHECKING:
    from agents.usecases.broker import AgentBroker

log = get_logger("agents.usecases.moc")


class ChangeImpact(GraphAgent):
    system = prompts.SYSTEM

    def __init__(self, reader, llm=None, broker: "AgentBroker | None" = None):
        super().__init__(reader, llm)
        self._broker = broker

    def tools(self) -> list:
        r = self._reader
        return [tools.connected_equipment(r), tools.failure_history(r),
                tools.governing_clauses(r), tools.documents_mentioning(r),
                tools.fix_procedures(r)]

    async def assess(self, proposal: ChangeProposal,
                     graph_version: int = 0) -> ImpactAssessment:
        reasoned = await self.reason(prompts.task(proposal), {proposal.tag})
        # _finish does a blocking Neo4j read (document_names); off the loop
        result = await asyncio.to_thread(self._finish, proposal, reasoned,
                                         graph_version)

        # Broker enrichment: append compliance flags to governing_clauses
        if self._broker:
            compliance_flags = await asyncio.to_thread(
                self._broker.get_compliance_flags, proposal.tag
            )
            for flag in compliance_flags:
                clause_label = f"[COMPLIANCE ALERT] {flag}"
                if clause_label not in result.governing_clauses:
                    result.governing_clauses.append(clause_label)
            if compliance_flags:
                log.info("moc assessment enriched with compliance flags",
                         tag=proposal.tag, flags=len(compliance_flags))

        return result

    async def assess_stream(self, proposal: ChangeProposal,
                            graph_version: int = 0):
        """assess(), streamed. Yields ('step', tool_name) as the agent gathers
        evidence, ('token', delta) as the assessment is written, and finally
        ('done', ImpactAssessment) - the structured envelope, which can only be
        harvested once the whole answer exists."""
        async for kind, payload in self.reason_stream(prompts.task(proposal),
                                                      {proposal.tag}):
            if kind == "reasoned":
                result = await asyncio.to_thread(self._finish, proposal,
                                                 payload, graph_version)
                yield "done", result
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
