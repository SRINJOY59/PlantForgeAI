"""Turning what the agent did into what the reviewer gets.

The body is the model's prose. The lists are not: affected_equipment,
documents_to_revise and governing_clauses are read back out of what the tools
actually returned, the same way docs_from_trace reads citations. So the model
cannot invent a clause into governing_clauses - it can only invent one into
body, where check_grounding catches it and marks the assessment unverified.

That split is the whole reason this module exists. A structured field that a
reviewer might paste into a statutory form has to be a fact about the graph,
not a claim about it.
"""

from plantmind_core.schemas import Citation, ImpactAssessment

# tool name -> (row key, list to collect it into)
_HARVEST = {
    "get_connected_equipment": ("tag", "affected_equipment"),
    "get_documents_mentioning": ("document", "documents_to_revise"),
    "get_governing_clauses": ("clause", "governing_clauses"),
}


def build(proposal, reasoned, graph_version: int = 0) -> ImpactAssessment:
    harvested = _harvest(reasoned.trace)

    body = reasoned.answer
    if not reasoned.grounding.verified:
        body += ("\n\n[UNVERIFIED - the following tags were not found in the "
                 "assessment evidence and may be incorrect: "
                 + ", ".join(reasoned.grounding.ungrounded_tags) + "]")

    return ImpactAssessment(
        proposal=proposal,
        body=body,
        affected_equipment=harvested["affected_equipment"],
        documents_to_revise=harvested["documents_to_revise"],
        governing_clauses=harvested["governing_clauses"],
        citations=[Citation(doc_id=d, snippet="") for d in reasoned.docs],
        graph_version=graph_version,
        verified=reasoned.grounding.verified,
        unverified_claims=reasoned.grounding.ungrounded_tags)


def _harvest(trace: list) -> dict:
    """Read the structured fields out of the tool results the agent pulled.

    The agent chooses its own tools, so a field is empty when it never asked -
    which is honest. An empty documents_to_revise means "nobody looked", and a
    reviewer seeing an empty list is better served by that than by prose
    claiming the change touches nothing.
    """
    out = {key: [] for _, key in _HARVEST.values()}
    for tool_name, _, result in trace:
        spec = _HARVEST.get(tool_name)
        if not spec:
            continue
        row_key, out_key = spec
        for row in (result if isinstance(result, list) else []):
            value = row.get(row_key)
            if value and value not in out[out_key]:
                out[out_key].append(value)
    return {k: sorted(v) for k, v in out.items()}


def corrected_facts(trace: list) -> list:
    """Failures on this equipment that an engineer has already overturned.

    Not shown to the reviewer directly - it is here so a caller can assert the
    agent was actually handed the correction. If this is non-empty and the
    assessment reasons as though the document were still right, the feature is
    not working, whatever the prose says.
    """
    found = []
    for tool_name, _, result in trace:
        if tool_name != "get_failure_history":
            continue
        for row in (result if isinstance(result, list) else []):
            if row.get("corrected_by"):
                found.append(row)
    return found
