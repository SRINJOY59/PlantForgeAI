"""Where did this answer actually come from?

The old signal was len(evidence) - a count of what retrieval *fetched*, which
says nothing about what the answer *used*. Two irrelevant chunks scored "high
confidence", which is how an empty answer about barg came back looking as
trustworthy as a cited failure history.

This reads the answer instead. A citation is a claim about provenance, and it
is checkable: the document has to be one we actually put in front of the model.
Three outcomes, all deterministic, no second LLM call:

  documents  - it cited docs we gave it. The strong case.
  general    - it cited nothing, so it answered from what the model knows.
               Fine for "what is barg"; the badge says so and nobody mistakes
               it for a fact about this plant.
  unverified - it cited a document we never showed it. That is a fabricated
               provenance claim, and it is the one case that deserves red.
"""

import re

# [doc:7bb5d5e5e90aaeac] or [doc:7bb5d5e5e90aaeac p4]
DOC_RE = re.compile(r"\[doc:([^\]\s]+)")

Grounding = str            # "documents" | "general" | "unverified"


def cited_docs(text: str) -> set:
    return set(DOC_RE.findall(text or ""))


def classify(text: str, evidence: list) -> tuple:
    """-> (grounding, confidence). Both fall out of the same comparison."""
    cited = cited_docs(text)
    available = {e.doc_id for e in evidence}

    fabricated = cited - available
    if fabricated:
        # naming a document that was never in the context means the id came out
        # of the model, not out of retrieval
        return "unverified", "low"

    if not cited:
        return "general", "medium"

    # confidence now tracks corroboration - how many distinct documents the
    # answer actually leaned on - rather than how many chunks we happened to
    # fetch and it happened to ignore
    return "documents", "high" if len(cited) >= 2 else "medium"
