"""What the failure investigation asks the model. Split out for the same reason
moc keeps its prompts apart: the wording is the part that decides whether the
alert reads as a specific instruction or a vague worry."""

SYSTEM = """You are a reliability and process safety engineer investigating
an alarm or failure pattern in an industrial process plant. The plant may be
the Tennessee Eastman Process (TEP) benchmark — a real Eastman Chemical plant
with 8 species, 4 reactions, and known IDV fault modes. Use the tools to
gather the equipment's own history, sibling equipment's history, fix procedures,
and process connections.

Then write a SHORT alert for the maintenance/operations team, as markdown, in
exactly these three sections and nothing else:

**What happened**
One or two sentences: the alarm tag, value, limit, and unit area affected.
If an IDV fault code is active, name it and its meaning.

**Likely cause**
One or two sentences naming the mechanism, not the symptom. Reference the
IDV fault (e.g. IDV-4 = reactor coolant inlet temperature step) if active.
If the evidence points upstream, say which asset.

**First checks**
A numbered list of the specific actions to take, most important first.
One action per line. Name the procedure and the prior work order if the tools
returned them. For TEP: reference standard operating procedures by area
(REACTOR, SEPARATOR, STRIPPER, etc.).

Rules:
- Start directly with the first bold heading. No title, no horizontal rule,
  no preamble.
- Do not invent tags, procedures or numbers the tools did not return.
- Do not claim anything has been raised, scheduled, ordered or sent to SAP.
  You are writing a warning, not performing an action."""

TASK = ("Equipment area '{tag}' in the Tennessee Eastman Process has triggered "
        "a {mode}. \n"
        "Alarm details: {alarm_details}\n"
        "Sibling equipment sharing the '{family}' family history: {siblings}.\n"
        "Investigate the root cause and provide recommended first checks.")

TASK_LEGACY = ("Equipment {tag} has just logged failure mode '{mode}'. Sibling "
               "equipment sharing the '{family}' family has seen it too. "
               "Investigate and advise.")


def _diagnosis_prior(diagnosis: dict | None) -> str:
    """Fold the statistical diagnosis into the task as a prior to test, not a
    conclusion to repeat. It carries what the deterministic pipeline already
    found - the matched fault mode and the cascade order - so the model reasons
    from evidence the plant produced rather than from a bare tag. The wording is
    deliberately 'confirm or refute': the grounding check still holds every tag
    the model names to the graph, so a wrong prior cannot launder itself into a
    verified claim."""
    if not diagnosis:
        return ""
    matched = diagnosis.get("matched_fault")
    if not matched:
        return ""
    conf = diagnosis.get("confidence")
    conf_pct = f"{round(conf * 100)}%" if isinstance(conf, (int, float)) else "n/a"
    cascade = " -> ".join(
        f"{d.get('tag')}{'↑' if d.get('direction') == 'high' else '↓'}"
        for d in (diagnosis.get("cascade") or [])
    )
    return (
        f"\n\nStatistical diagnosis (deterministic, pre-computed - a prior to "
        f"confirm or refute, not ground truth): the live signature most "
        f"resembles known fault {matched} "
        f"({diagnosis.get('matched_label') or '?'}) at {conf_pct} confidence. "
        f"Observed cascade (first mover first): {cascade or 'n/a'}."
    )


def task(trigger, alert_context: dict | None = None) -> str:
    if alert_context:
        idvs = alert_context.get("active_idvs", [])
        idv_descs = alert_context.get("idv_descriptions", [])
        alarm_details = (
            f"Tag: {alert_context.get('tag_id', trigger.tag)}, "
            f"Level: {alert_context.get('alarm_level', 'H')}, "
            f"Value: {alert_context.get('value', '?')}, "
            f"Limit: {alert_context.get('limit', '?')}. "
            f"Active IDV faults: {[f'IDV-{i}: {d}' for i,d in zip(idvs, idv_descs)] or 'none'}.\n"
            f"Message: {alert_context.get('message', '')}"
        )
        alarm_details += _diagnosis_prior(alert_context.get("diagnosis"))
        siblings_str = ", ".join(
            s.get("tag", "") for s in trigger.siblings
        ) if trigger.siblings else "none found"
        return TASK.format(
            tag=trigger.tag,
            mode=trigger.mode,
            alarm_details=alarm_details,
            family=trigger.family,
            siblings=siblings_str,
        )
    return TASK_LEGACY.format(tag=trigger.tag, mode=trigger.mode,
                              family=trigger.family)
