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

# Matches [doc:ID], [doc:ID p4], [ID], or [ID p4]
DOC_RE = re.compile(r"\[(?:doc:)?([a-zA-Z0-9_-]{6,})(?:\s*p\d+)?\]")
HEX_WORD_RE = re.compile(r"\b([a-f0-9]{6,16})\b", re.I)

Grounding = str            # "documents" | "general" | "unverified"


def cited_docs(text: str, evidence: list = None) -> set:
    """Extract cited document IDs, resolving prefixes against evidence if available."""
    raw_cites = set(DOC_RE.findall(text or ""))
    
    if not evidence:
        return raw_cites
        
    available = {e.doc_id for e in evidence if e.doc_id}
    
    # Also check standalone hex words if enclosed in backticks or markdown
    for match in HEX_WORD_RE.findall(text or ""):
        for a in available:
            if a.startswith(match.lower()) and len(match) >= 6:
                raw_cites.add(a)

    resolved = set()
    for c in raw_cites:
        matched = False
        for a in available:
            if a == c or a.startswith(c) or c.startswith(a):
                resolved.add(a)
                matched = True
                break
        if not matched:
            resolved.add(c)
            
    return resolved


def classify(text: str, evidence: list) -> tuple:
    """-> (grounding, confidence). Both fall out of the same comparison."""
    available = {e.doc_id for e in evidence if e.doc_id}
    cited = cited_docs(text, evidence)

    # Check if any cited document is completely absent/fabricated
    fabricated = {c for c in cited if not any(a == c or a.startswith(c) or c.startswith(a) for a in available)}
    
    if fabricated:
        # naming a document that was never in the context means the id came out
        # of the model, not out of retrieval
        return "unverified", "low"

    valid_cites = cited & available
    if not valid_cites:
        return "general", "medium"

    # confidence tracks corroboration - how many distinct documents the
    # answer actually leaned on
    return "documents", "high" if len(valid_cites) >= 2 else "medium"

