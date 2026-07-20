"""Agent Broker — lightweight mediator for inter-agent collaboration.

Each agent in this service is designed to work entirely on its own. But some
questions are better answered by a peer's domain knowledge than by adding more
tools to a single agent:

  - A Permit-to-Work is stronger if it knows a ComplianceScanner just flagged
    the target equipment as overdue for a statutory inspection.
  - A Management-of-Change assessment should note if the change touches
    equipment that is already under an open compliance flag.
  - A Report should include an overdue-inspection table without the report agent
    having to re-implement the compliance logic.
  - The Field Copilot should deliver a safety briefing at session start if the
    work order's equipment has known hazards in the failure history.

The broker owns those call-outs. It holds optional weak references to its peer
agents; if a peer is not wired (e.g. in tests or simple deployments), the call
returns a safe empty default.

Rules that keep this from becoming spaghetti:
  - The dependency graph is a DAG.  ComplianceScanner and InvestigatorAgent are
    pure providers and never call back into the broker.
  - Agents call the broker, never each other directly.  This keeps coupling
    at one choke-point that is easy to trace.
  - Every broker method has a safe default so the caller never needs to branch
    on whether the broker is wired.
"""

import asyncio
import datetime
from typing import TYPE_CHECKING

from plantmind_core.telemetry import get_logger

if TYPE_CHECKING:
    from agents.usecases.compliance import ComplianceScanner
    from agents.usecases.failure_rca import InvestigatorAgent
    from agents.usecases.permit_to_work import PermitToWorkAgent

log = get_logger("agents.broker")


class AgentBroker:
    """Mediates capability sharing between agents.

    Instantiate once at startup in main.py, wire the peer agents, then pass
    the broker to each agent that needs it.  Agents that don't declare a
    broker dependency continue to work unchanged.
    """

    def __init__(self):
        self._compliance: "ComplianceScanner | None" = None
        self._investigator: "InvestigatorAgent | None" = None
        self._permit: "PermitToWorkAgent | None" = None

    # ── Wiring ──────────────────────────────────────────────────────────────

    def register_compliance(self, scanner: "ComplianceScanner") -> "AgentBroker":
        self._compliance = scanner
        return self

    def register_investigator(self, investigator: "InvestigatorAgent") -> "AgentBroker":
        self._investigator = investigator
        return self

    def register_permit(self, permit: "PermitToWorkAgent") -> "AgentBroker":
        self._permit = permit
        return self

    # ── Capability: compliance flags ─────────────────────────────────────────

    def get_compliance_flags(self, tag: str) -> list[str]:
        """Return human-readable overdue-inspection strings for *tag*.

        Uses today's date deterministically — no LLM involved.  Returns [] if
        the compliance scanner is not wired or finds nothing.
        """
        if self._compliance is None:
            return []
        today = datetime.date.today().isoformat()
        try:
            alerts = self._compliance.scan(today, graph_version=0)
        except Exception as exc:
            log.warning("compliance scan failed in broker", error=str(exc))
            return []
        flags = []
        for alert in alerts:
            if alert.equipment and alert.equipment == tag:
                flags.append(alert.title)
        log.debug("compliance flags fetched", tag=tag, count=len(flags))
        return flags

    # ── Capability: hazard summary from failure history ──────────────────────

    async def get_hazard_summary(self, tag: str) -> str:
        """Ask the InvestigatorAgent for a concise hazard summary for *tag*.

        Returns an empty string if the investigator is not wired or if the
        agent call fails.  The caller must treat '' as 'no additional context'.
        """
        if self._investigator is None:
            return ""
        try:
            # Build a lightweight trigger-like object the investigator prompt accepts
            class _FakeTrigger:
                def __init__(self, t):
                    self.tag = t
                    self.mode = "known_hazards"
                    self.family = t
                    self.siblings = []
                    self.count = 1
                    self.graph_version = 0

            alert = await self._investigator.investigate(_FakeTrigger(tag))
            log.debug("hazard summary fetched", tag=tag,
                      verified=alert.verified)
            # Return a trimmed version so it fits inside a session briefing
            return alert.body[:800].strip() if alert.body else ""
        except Exception as exc:
            log.warning("hazard summary fetch failed in broker",
                        tag=tag, error=str(exc))
            return ""

    # ── Capability: safety briefing for Field Copilot ─────────────────────

    async def get_safety_briefing(self, tag: str) -> str:
        """Combine compliance flags + hazard summary into a pre-session briefing.

        Called by FieldCopilotAgent at session creation time.  The result is
        prepended to the first spoken step so the worker hears the hazard
        context before any hands-on work begins.

        Returns '' when nothing is outstanding.
        """
        flags = await asyncio.to_thread(self.get_compliance_flags, tag)
        hazards = await self.get_hazard_summary(tag)

        parts = []
        if flags:
            parts.append("SAFETY BRIEFING. The following compliance flags are "
                         "outstanding for this equipment: "
                         + "; ".join(flags) + ".")
        if hazards:
            parts.append("Known hazard context: " + hazards)

        briefing = " ".join(parts).strip()
        if briefing:
            log.info("safety briefing assembled", tag=tag,
                     compliance_flags=len(flags), has_hazards=bool(hazards))
        return briefing
