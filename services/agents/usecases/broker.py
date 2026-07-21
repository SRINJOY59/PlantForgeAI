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

The broker owns those call-outs. It holds optional weak references to its peer
agents; if a peer is not wired (e.g. in tests or simple deployments), the call
returns a safe empty default.

Rules that keep this from becoming spaghetti:
  - The dependency graph is a DAG.  ComplianceScanner is a
    pure provider and never calls back into the broker.
  - Agents call the broker, never each other directly.  This keeps coupling
    at one choke-point that is easy to trace.
  - Every broker method has a safe default so the caller never needs to branch
    on whether the broker is wired.
"""

import datetime
from typing import TYPE_CHECKING

from plantmind_core.telemetry import get_logger

if TYPE_CHECKING:
    from agents.usecases.compliance import ComplianceScanner
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
        self._permit: "PermitToWorkAgent | None" = None

    # ── Wiring ──────────────────────────────────────────────────────────────

    def register_compliance(self, scanner: "ComplianceScanner") -> "AgentBroker":
        self._compliance = scanner
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

