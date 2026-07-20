"""Permit-to-Work agent.

Same engine as the change impact assessment — graph tools, system prompt,
grounding check — but the artifact is a WorkPermit rather than an
ImpactAssessment.  The distinction matters: a MOC assessment answers 'what
does this change touch?'; a PTW answers 'what must be controlled before
anyone touches it?'

The agent is triggered by a person (the job requester), never by a delta.
It lives in main.py, not consumer.py.

When wired with an AgentBroker the permit drafting also:
  - Fetches compliance flags for the target equipment and injects them into
    identified_hazards so the permit authority sees outstanding inspections.
"""

import asyncio
from typing import TYPE_CHECKING

from plantmind_core.schemas import PermitRequest, WorkPermit
from plantmind_core.telemetry import get_logger

from agents import tools
from agents.usecases.base import GraphAgent
from agents.usecases.permit_to_work import permit_builder, prompts

if TYPE_CHECKING:
    from agents.usecases.broker import AgentBroker

log = get_logger("agents.usecases.permit_to_work")


class PermitToWorkAgent(GraphAgent):
    """Drafts a pre-populated Permit-to-Work checklist from graph evidence.

    Optionally accepts an AgentBroker to pull compliance flags from the
    ComplianceScanner and prepend them to the permit's identified_hazards.
    """

    system = prompts.SYSTEM

    def __init__(self, reader, llm=None, broker: "AgentBroker | None" = None):
        super().__init__(reader, llm)
        self._broker = broker

    def tools(self) -> list:
        r = self._reader
        return [
            tools.connected_equipment(r),   # isolation boundary
            tools.failure_history(r),        # known hazards from operating history
            tools.governing_clauses(r),      # statutory obligations
            tools.fix_procedures(r),         # applicable SOPs
            tools.work_orders(r),            # what was found last time
            tools.documents_mentioning(r),   # any other docs that reference the tag
        ]

    async def draft_permit(self, request: PermitRequest,
                           graph_version: int = 0) -> WorkPermit:
        given = {request.tag}
        reasoned = await self.reason(prompts.task(request), given)

        names = await asyncio.to_thread(
            self._reader.document_names, reasoned.docs
        )
        result = permit_builder.build(request, reasoned, graph_version, names)

        # Broker enrichment: prepend outstanding compliance flags as hazards
        if self._broker:
            compliance_flags = await asyncio.to_thread(
                self._broker.get_compliance_flags, request.tag
            )
            for flag in compliance_flags:
                hazard_label = f"[COMPLIANCE] {flag}"
                if hazard_label not in result.identified_hazards:
                    result.identified_hazards.insert(0, hazard_label)
            if compliance_flags:
                log.info("permit enriched with compliance flags",
                         tag=request.tag, flags=len(compliance_flags))

        log.info(
            "permit drafted",
            tag=request.tag,
            permit_type=result.permit_type,
            isolation_points=len(result.isolation_points),
            hazards=len(result.identified_hazards),
            tools_used=len(reasoned.trace),
            verified=result.verified,
        )
        return result

    async def draft_permit_stream(self, request: PermitRequest,
                                  graph_version: int = 0):
        """Streamed variant: yields ('step', tool_name) as evidence is gathered,
        ('token', delta) as the permit narrative is written, and finally
        ('done', WorkPermit) when the full structured artifact is available.
        """
        async for kind, payload in self.reason_stream(
            prompts.task(request), {request.tag}
        ):
            if kind == "reasoned":
                names = await asyncio.to_thread(
                    self._reader.document_names, payload.docs
                )
                result = permit_builder.build(request, payload, graph_version, names)
                log.info("permit drafted (stream)",
                         tag=request.tag, permit_type=result.permit_type,
                         verified=result.verified)
                yield "done", result
            else:
                yield kind, payload
