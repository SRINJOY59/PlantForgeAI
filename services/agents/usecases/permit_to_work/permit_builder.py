"""Harvesting structured permit fields from the agent's tool trace.

The body is the model's prose.  The structured lists — isolation_points,
identified_hazards, governing_clauses, procedures_to_follow — are read back
out of what the tools actually returned, the same way moc/assessment.py reads
affected_equipment.  The model cannot invent a valve into isolation_points; it
can only invent one into body, where check_grounding will catch it.

That split is the whole safety argument.  A permit authority who pastes a list
of isolation points into a CMMS has to be able to trust that the list came from
the plant's own records, not from a language model guessing.
"""

import re

from plantmind_core.schemas import Citation, PermitRequest, WorkPermit

# Tool name -> (row key, output list field)
_HARVEST = {
    "get_connected_equipment": ("tag", "isolation_points"),
    "get_governing_clauses":   ("clause", "governing_clauses"),
    "get_fix_procedures":      ("procedure", "procedures_to_follow"),
}

# Keywords that suggest active hazards when seen in failure-history causes
_HAZARD_KEYWORDS = {
    "leak":         "Fluid leak / release hazard",
    "seal":         "Seal failure — potential liquid / vapour release",
    "fire":         "Fire / ignition hazard",
    "overpressure": "Overpressure hazard",
    "vibration":    "Mechanical vibration — structural fatigue risk",
    "cavitation":   "Cavitation — impeller / casing damage risk",
    "overheating":  "Overheating — thermal burn / fire risk",
    "corrosion":    "Corrosion — material thinning / leak risk",
    "electrical":   "Electrical hazard",
    "gas":          "Toxic / flammable gas release hazard",
}

# Permit type classification from work description keywords
_PERMIT_TYPE_RULES = [
    (re.compile(r"\b(weld|cut|grind|spark|flame|hot.?work)\b", re.I), "Hot Work"),
    (re.compile(r"\b(confined.?space|vessel|tank|manhole|enter)\b", re.I), "Confined Space Entry"),
    (re.compile(r"\b(electrical|motor|panel|MCC|switchgear|de.?energ)\b", re.I), "Electrical Isolation"),
    (re.compile(r"\b(cold.?work|mechanical|replac|overhaul|inspect)\b", re.I), "Cold Work"),
]

_DEFAULT_PPE = [
    "Hard hat (EN397 / ANSI Z89.1)",
    "Safety glasses or face shield",
    "Steel-toed safety footwear",
    "Chemical-resistant gloves",
    "High-visibility vest",
]

_EXTRA_PPE = {
    "Hot Work":               ["Fire-retardant coverall (FR clothing)", "Welding gloves & face shield"],
    "Confined Space Entry":   ["Full-body harness & lifeline", "Gas monitor (O₂ / LEL / H₂S / CO)", "SCBA or supplied-air respirator"],
    "Electrical Isolation":   ["Arc-flash rated PPE (appropriate cal/cm² rating)", "Insulated tools"],
}


def classify_permit(work_description: str) -> str:
    for pattern, permit_type in _PERMIT_TYPE_RULES:
        if pattern.search(work_description):
            return permit_type
    return "General Maintenance"


def hazards_from_trace(trace: list) -> list[str]:
    """Extract known hazards from failure-history tool results."""
    found = []
    for tool_name, _, result in trace:
        if tool_name != "get_failure_history":
            continue
        for row in (result if isinstance(result, list) else []):
            for cause in row.get("causes", []):
                for kw, label in _HAZARD_KEYWORDS.items():
                    if kw in cause.lower() and label not in found:
                        found.append(label)
            for mode in [row.get("mode", "")]:
                for kw, label in _HAZARD_KEYWORDS.items():
                    if kw in mode.lower() and label not in found:
                        found.append(label)
    return found


def build(request: PermitRequest, reasoned, graph_version: int,
          names: dict | None = None) -> WorkPermit:
    names = names or {}

    # Harvest structured lists from tool evidence — model can't inject these
    harvested: dict[str, list[str]] = {field: [] for _, field in _HARVEST.values()}
    for tool_name, _, result in reasoned.trace:
        spec = _HARVEST.get(tool_name)
        if not spec:
            continue
        row_key, out_key = spec
        for row in (result if isinstance(result, list) else []):
            value = row.get(row_key)
            if value and value not in harvested[out_key]:
                harvested[out_key].append(value)

    permit_type = classify_permit(request.work_description)
    ppe = list(_DEFAULT_PPE)
    ppe.extend(_EXTRA_PPE.get(permit_type, []))

    body = reasoned.answer
    if not reasoned.grounding.verified:
        body += (
            "\n\n[UNVERIFIED — the following tags were not found in the "
            "permit evidence and may be incorrect: "
            + ", ".join(reasoned.grounding.ungrounded_tags) + "]"
        )

    return WorkPermit(
        request=request,
        body=body,
        permit_type=permit_type,
        isolation_points=sorted(harvested["isolation_points"]),
        identified_hazards=hazards_from_trace(reasoned.trace),
        required_ppe=ppe,
        governing_clauses=sorted(harvested["governing_clauses"]),
        procedures_to_follow=sorted(harvested["procedures_to_follow"]),
        citations=[
            Citation(doc_id=d, snippet="",
                     filename=names.get(d) or names.get(f"doc:{d}"))
            for d in reasoned.docs
        ],
        graph_version=graph_version,
        verified=reasoned.grounding.verified,
        unverified_claims=reasoned.grounding.ungrounded_tags,
    )
