"""The agentic layer. A deterministic watcher decides THAT something is
worth investigating; this LLM agent decides WHAT it means and what to do,
by calling graph tools of its own choosing - failure history, fix
procedures, connected equipment, work-order actions - and synthesising a
recommendation. This is the 'connect the dots no one person can' step."""

from plantmind_core.schemas import Alert, Citation
from plantmind_core.telemetry import get_logger

from agents import tools
from agents.usecases.base import GraphAgent

log = get_logger("agents.usecases.failure_rca")

SYSTEM = """You are a reliability engineer investigating a failure pattern
in a process plant. Use the tools to gather the equipment's own history,
its sibling equipment's history, the procedures that fix it, and its
process connections. Then write a SHORT alert for the maintenance team:
what is recurring, the likely shared root cause, and the specific first
checks to make before returning the equipment to service - naming the
procedure and the prior work order that fixed it if you find them. Be
concrete. Do not invent tags, procedures or numbers not returned by tools."""

TASK = ("Equipment {tag} has just logged failure mode '{mode}'. Sibling "
        "equipment sharing the '{family}' family has seen it too. "
        "Investigate and advise.")


class InvestigatorAgent(GraphAgent):
    """Wraps a ToolAgent with graph tools bound to one AgentReader."""

    system = SYSTEM

    def tools(self) -> list:
        r = self._reader
        return [tools.failure_history(r), tools.sibling_history(r),
                tools.fix_procedures(r), tools.connected_equipment(r),
                tools.work_orders(r)]

    async def investigate(self, trigger) -> Alert:
        # Layer 1: every tag the agent named must trace to its evidence
        given = {trigger.tag, trigger.family,
                 *(s["tag"] for s in trigger.siblings)}
        reasoned = await self.reason(
            TASK.format(tag=trigger.tag, mode=trigger.mode,
                        family=trigger.family), given)

        grounding = reasoned.grounding
        log.info("investigation done", tag=trigger.tag, mode=trigger.mode,
                 tools_used=len(reasoned.trace), verified=grounding.verified,
                 ungrounded=grounding.ungrounded_tags)

        body = reasoned.answer
        if not grounding.verified:
            body += ("\n\n[UNVERIFIED - the following tags were not found in "
                     "the investigation evidence and may be incorrect: "
                     + ", ".join(grounding.ungrounded_tags) + "]")

        # an ungrounded alert can't be critical - trust is capped by evidence
        recurring_pattern = trigger.siblings and trigger.count >= 2
        severity = "critical" if (recurring_pattern and grounding.verified) \
            else "warning"
        return Alert(
            kind="failure_pattern", severity=severity,
            title=f"Recurring failure pattern: {trigger.tag} {trigger.mode}",
            body=body, equipment=trigger.tag,
            citations=[Citation(doc_id=d, snippet="") for d in reasoned.docs],
            fingerprint=f"failure:{trigger.tag}:{trigger.mode}:{trigger.count}",
            graph_version=trigger.graph_version,
            verified=grounding.verified,
            unverified_claims=grounding.ungrounded_tags)
