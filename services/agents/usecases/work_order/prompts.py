"""What the work-order drafter asks the model, and - more importantly - what
it does not ask.

The model is given the investigation that already happened and is asked for
exactly two paragraphs: what is actually wrong, and what to do about it. It is
never asked for the asset list, the prior work orders, the procedures or the
priority. Those are harvested from the tool results or derived from a rule,
because a work order is an instruction to put a spanner on live plant, and the
part of it that can be invented should be as small as the job allows.
"""

SYSTEM = """You are a maintenance planner writing the two narrative fields of
a corrective work order, from a failure investigation that has already been
carried out for you.

root_cause: what is actually failing and why, in 1-3 sentences. Name the
mechanism, not the symptom - "seal fails because suction-side starvation from
a fouled strainer drives cavitation", not "seal keeps failing". If the
evidence points at a shared cause across sibling equipment, say so.

recommended_fix: what the technician should actually do, as specific ordered
actions. Lead with whatever must happen BEFORE the obvious repair, because the
whole value of this is stopping a repeat. Reference procedures and prior work
orders only if they appear in the evidence below.

Rules:
- Use only tags, procedures, work orders and numbers that appear in the
  evidence. Do not invent identifiers.
- Do not restate the equipment list; it is recorded separately.
- No preamble, no headings, no markdown. Two plain fields."""

TASK = """Equipment: {tag}
Failure mode: {mode}

The investigation concluded:
{finding}

Evidence gathered by the investigation:
{evidence}

Write root_cause and recommended_fix for the corrective work order."""


def task(tag: str, mode: str, finding: str, evidence: str) -> str:
    return TASK.format(tag=tag, mode=mode, finding=finding, evidence=evidence)
