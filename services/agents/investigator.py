"""The agentic layer. A deterministic watcher decides THAT something is
worth investigating; this LLM agent decides WHAT it means and what to do,
by calling graph tools of its own choosing - failure history, fix
procedures, connected equipment, work-order actions - and synthesising a
recommendation. This is the 'connect the dots no one person can' step."""

from plantmind_core.llm import Tier, Tool, ToolAgent
from plantmind_core.schemas import Alert, Citation
from plantmind_core.telemetry import get_logger

log = get_logger("agents.investigator")

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


class InvestigatorAgent:
    """Wraps a ToolAgent with graph tools bound to one AgentReader."""

    def __init__(self, reader, llm=None):
        self._reader = reader
        self._llm = llm

    def _tools(self) -> list:
        r = self._reader
        return [
            Tool("get_failure_history",
                 "Failure modes and occurrence counts for an equipment tag.",
                 _one_tag_schema(), lambda tag: r.equipment_failures(
                     _id_for(tag))),
            Tool("get_sibling_history",
                 "Failure history of sibling equipment (same family stem, "
                 "e.g. 'P-101') for a given failure mode.",
                 {"type": "object", "properties": {
                     "family": {"type": "string"},
                     "mode": {"type": "string"},
                     "exclude_tag": {"type": "string"}},
                  "required": ["family", "mode", "exclude_tag"]},
                 r.family_history),
            Tool("get_fix_procedures",
                 "Procedures that fix a piece of equipment.",
                 _one_tag_schema(), r.procedures_for),
            Tool("get_connected_equipment",
                 "Equipment and instruments directly connected in the process.",
                 _one_tag_schema(), r.connected_equipment),
            Tool("get_work_orders",
                 "Recent work orders and the actions taken on an equipment tag.",
                 _one_tag_schema(), r.work_orders_for),
        ]

    async def investigate(self, trigger) -> Alert:
        agent = ToolAgent(self._tools(), tier=Tier.MID, max_steps=6,
                          llm=self._llm)
        result = await agent.run(
            SYSTEM, TASK.format(tag=trigger.tag, mode=trigger.mode,
                                family=trigger.family))
        log.info("investigation done", tag=trigger.tag, mode=trigger.mode,
                 steps=result.steps, tools_used=len(result.trace))

        docs = _docs_from_trace(result.trace)
        severity = "critical" if (trigger.siblings and trigger.count >= 2) \
            else "warning"
        return Alert(
            kind="failure_pattern", severity=severity,
            title=f"Recurring failure pattern: {trigger.tag} {trigger.mode}",
            body=result.answer, equipment=trigger.tag,
            citations=[Citation(doc_id=d, snippet="") for d in docs],
            fingerprint=f"failure:{trigger.tag}:{trigger.mode}:{trigger.count}",
            graph_version=trigger.graph_version)


def _one_tag_schema() -> dict:
    return {"type": "object",
            "properties": {"tag": {"type": "string"}},
            "required": ["tag"]}


def _id_for(tag: str) -> str:
    return f"equip:{tag}"


def _docs_from_trace(trace) -> list:
    docs = set()
    for _, _, result in trace:
        for row in (result if isinstance(result, list) else []):
            docs.update(row.get("docs") or [])
            if row.get("doc_id"):
                docs.add(row["doc_id"])
    return sorted(docs)
