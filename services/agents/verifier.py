"""Grounding check for agent output - Layer 1 of the trust model. Every
equipment/instrument tag the agent names in its recommendation must have
appeared either in the trigger it was handed or in a tool result it
actually pulled. A tag from nowhere is a hallucination: the alert is kept
(so nothing is silently dropped) but marked unverified so no downstream
reader - human or agent - treats it as fact.

Deterministic on purpose: catching an invented tag is a crisp string
question, not a job for a second LLM."""

import json
from dataclasses import dataclass

from plantmind_core import tags


@dataclass
class Grounding:
    verified: bool
    ungrounded_tags: list


def check_grounding(answer: str, trace: list, given: set) -> Grounding:
    """given: tags supplied to the agent by construction (the trigger).
    trace: [(tool_name, args, result)] the agent actually called."""
    evidence = _evidence_text(trace, given)
    claimed = {t for t, _, _ in tags.find_tags(answer)}
    ungrounded = sorted(t for t in claimed if t not in evidence)
    return Grounding(verified=not ungrounded, ungrounded_tags=ungrounded)


def _evidence_text(trace: list, given: set) -> set:
    """Every tag that legitimately backs a claim: the given tags plus every
    tag appearing anywhere in a tool result."""
    grounded = set(given)
    blob = json.dumps([r for _, _, r in trace], default=str)
    for tag, _, _ in tags.find_tags(blob):
        grounded.add(tag)
    return grounded
