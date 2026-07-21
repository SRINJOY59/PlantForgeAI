"""Turns a finished failure investigation into a corrective work order draft.

It deliberately does NOT run its own tool loop. The investigation has already
walked the graph - failure history, siblings, procedures, connections, prior
work orders - and that trace is the evidence. Re-reasoning over the same graph
would cost a second multi-tool LLM run to learn what we already know, and would
let the two artifacts disagree about the same failure. So this harvests the
trace it is handed, and spends exactly one structured call on the two fields a
human actually needs written in prose.

The split matters more here than anywhere else in the service. An assessment is
read by an engineer who will argue with it; a work order is executed. So the
assets, the prior work orders and the procedures are lifted verbatim out of
tool results, the priority comes from a rule, and the model's reach is limited
to root_cause and recommended_fix - which are then grounding-checked like any
other prose in this codebase.
"""

from plantmind_core.llm import Tier
from plantmind_core.schemas import Citation, WorkOrderDraft, WorkOrderDraftProse
from plantmind_core.telemetry import get_logger

from agents.verifier import check_grounding
from agents.usecases.work_order import prompts

log = get_logger("agents.usecases.work_order")

# Which key of a tool's result rows carries the fact we want. Reading by tool
# name rather than sniffing every row keeps a work order from quietly picking
# up, say, a sibling's tag as a procedure because both rows had the key.
HARVEST = {
    "get_sibling_history":     ("tag",       "affected_equipment"),
    "get_connected_equipment": ("tag",       "affected_equipment"),
    "get_work_orders":         ("wo_id",     "prior_work_orders"),
    "get_fix_procedures":      ("procedure", "procedures"),
    "get_governing_clauses":   ("clause",    "governing_clauses"),
    "get_failure_history":     ("mode",      "failure_modes"),
}


def harvest(trace: list) -> dict:
    """Pull the fact lists out of what the tools returned.

    Order is preserved and duplicates dropped: a planner reading 'P-101B,
    P-101B, FT-103' loses confidence in the whole document, and dict.fromkeys
    is the cheapest way to stay stable rather than sorting into arbitrary
    alphabetical order.
    """
    out = {v: [] for _, v in HARVEST.values()}
    for name, _args, result in trace:
        spec = HARVEST.get(name)
        if not spec or not isinstance(result, list):
            continue
        key, field = spec
        for row in result:
            if isinstance(row, dict) and row.get(key):
                out[field].append(str(row[key]))
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}


def derive_priority(trigger, clauses: list, verified: bool) -> str:
    """Urgency by rule, not by vibe.

    A recurring failure across siblings is the case this whole product exists
    to catch, so it outranks a one-off. A statutory clause on the asset raises
    it again - that is an inspection someone can be prosecuted over. And an
    ungrounded draft is capped: if we could not trace what the model said, we
    are not entitled to tell a planner to drop everything.
    """
    siblings = len(getattr(trigger, "siblings", []) or [])
    count = getattr(trigger, "count", 1) or 1
    recurring = siblings > 0 and count >= 2

    if not verified:
        return "medium" if recurring else "low"
    if recurring and clauses:
        return "immediate"
    if recurring or clauses:
        return "high"
    return "medium" if count >= 2 else "low"


def _evidence_text(trace: list, limit=2400) -> str:
    """The tool results, flattened for the prompt. Truncated because a long
    investigation can outgrow the context, and the tail of a work-order
    history is the least useful part of it."""
    lines = []
    for name, _args, result in trace:
        if not isinstance(result, list) or not result:
            continue
        lines.append(f"{name}:")
        for row in result[:8]:
            lines.append(f"  {row}")
    return "\n".join(lines)[:limit] or "(no tool evidence)"


def from_compliance(item: dict, graph_version: int = 0) -> WorkOrderDraft:
    """A statutory inspection that is due, as a preventive work order.

    No LLM anywhere in here, and that is the point rather than an optimisation.
    The cause is not a judgement - the obligation exists and the date has
    passed - and the fix is the inspection the standard already names. There is
    nothing to reason about, so nothing is left for a model to get wrong, and
    verified=True is a fact rather than the output of a grounding check.

    PM02 because this is preventive: the asset has not failed, it is due.
    """
    equip = item.get("equipment") or ""
    standard = item.get("standard") or ""
    kind = item.get("inspection_type") or "Inspection"
    due = item.get("next_due") or ""
    last = item.get("last_inspection") or ""
    overdue = item.get("status") == "overdue"

    cause = (f"{kind} of {equip} required by {standard} "
             f"{'was due' if overdue else 'falls due'} {due}"
             + (f"; last carried out {last}." if last else "."))
    fix = (f"Carry out the {kind.lower()} of {equip} to {standard}"
           + (f" (revision {item['revision']})" if item.get("revision") else "")
           + ". Record the result against the asset so the next due date rolls "
             "forward.")

    return WorkOrderDraft(
        equipment=equip,
        failure_mode="",
        affected_equipment=[equip] if equip else [],
        governing_clauses=[standard] if standard else [],
        citations=[Citation(doc_id=item["doc_id"], page=item.get("page"),
                            snippet="")] if item.get("doc_id") else [],
        root_cause=cause,
        recommended_fix=fix,
        order_type="PM02",
        # a missed statutory inspection is an exposure that grows with time,
        # so an overdue one outranks one that is merely approaching
        priority="high" if overdue else "medium",
        graph_version=graph_version,
        verified=True)


class WorkOrderDrafter:
    """One structured LLM call over an investigation that already happened."""

    def __init__(self, llm=None):
        self._llm = llm

    async def draft(self, trigger, reasoned, graph_version: int) -> WorkOrderDraft:
        facts = harvest(reasoned.trace)

        tag = getattr(trigger, "tag", "")
        mode = getattr(trigger, "mode", "")
        # the trigger's own tag belongs at the front of the asset list: it is
        # the reason the work order exists, and harvest only sees siblings
        affected = list(dict.fromkeys([tag, *facts["affected_equipment"]]))
        affected = [a for a in affected if a]

        prose = await self._prose(tag, mode, reasoned)

        # Same grounding gate as the alert: every tag the model named has to
        # appear in the evidence the tools returned, or it is called out.
        given = {tag, getattr(trigger, "family", ""),
                 *(s.get("tag", "") for s in getattr(trigger, "siblings", []) or [])}
        grounding = check_grounding(
            f"{prose.root_cause}\n{prose.recommended_fix}", reasoned.trace,
            {g for g in given if g})

        priority = derive_priority(trigger, facts["governing_clauses"],
                                   grounding.verified)

        draft = WorkOrderDraft(
            equipment=tag, failure_mode=mode,
            affected_equipment=affected,
            prior_work_orders=facts["prior_work_orders"],
            procedures=facts["procedures"],
            governing_clauses=facts["governing_clauses"],
            citations=[Citation(doc_id=d, snippet="") for d in reasoned.docs],
            root_cause=prose.root_cause,
            recommended_fix=prose.recommended_fix,
            order_type="PM01",
            priority=priority,
            graph_version=graph_version,
            verified=grounding.verified,
            unverified_claims=grounding.ungrounded_tags)

        log.info("work order drafted", tag=tag, priority=priority,
                 affected=len(affected), procedures=len(facts["procedures"]),
                 prior_wos=len(facts["prior_work_orders"]),
                 verified=grounding.verified)
        return draft

    async def _prose(self, tag, mode, reasoned) -> WorkOrderDraftProse:
        """The model's whole surface area: two fields, schema-constrained.

        Falls back to the investigation's own narrative rather than failing the
        draft - a work order carrying the alert text is still actionable, and
        losing the draft entirely because one call timed out is worse.
        """
        from plantmind_core.llm import LLM
        llm = self._llm or LLM.from_settings()
        try:
            return await llm.structured(
                [{"role": "system", "content": prompts.SYSTEM},
                 {"role": "user", "content": prompts.task(
                     tag, mode, reasoned.answer, _evidence_text(reasoned.trace))}],
                WorkOrderDraftProse, tier=Tier.MID)
        except Exception as e:
            log.warning("work order prose failed, falling back to the "
                        "investigation narrative", tag=tag, error=str(e)[:200])
            return WorkOrderDraftProse(
                root_cause=reasoned.answer[:1200],
                recommended_fix="See root cause. Prose generation failed; "
                                "the investigation narrative is reproduced above.")
