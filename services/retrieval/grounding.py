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

# [doc:7bb5d5e5e90aaeac], or [doc:7bb5d5e5e90aaeac p4] with the page attached.
#
# Any id is accepted after the prefix, because the prefix is the model stating
# outright that this is a citation - there is nothing to disambiguate. A single
# pattern that also had to cover the bare form below was given a 6-character
# minimum to keep it off markdown footnotes, and that minimum silently applied
# here too: every document whose id was shorter than six characters stopped
# being read as a citation at all, so answers that cited correctly were graded
# "general" and listed no sources.
DOC_RE = re.compile(r"\[doc:([^\]\s]+?)(?:\s+p\d+)?\]")

# A bare [7bb5d5e5e90aaeac], which some models emit instead of the prefixed
# form. This one is genuinely ambiguous with markdown footnotes and list
# markers, so it has to look like a document hash - long, and hex. [4], [note]
# and [see below] are not citations.
BARE_DOC_RE = re.compile(r"\[([a-f0-9]{6,})(?:\s+p\d+)?\]", re.I)

# The same hash sitting in prose or backticks rather than brackets.
HEX_WORD_RE = re.compile(r"\b([a-f0-9]{6,16})\b", re.I)

# Below this, a "prefix" is a coincidence rather than a truncated hash: with
# ids as short as a couple of characters, prefix matching would let one
# document absorb every citation in the answer.
MIN_PREFIX = 6

Grounding = str            # "documents" | "general" | "unverified"


def _resolve(cited: str, available: set) -> str | None:
    """The document `cited` refers to, or None if it refers to none of them.

    Models truncate: asked to cite 7bb5d5e5e90aaeac they will often write
    7bb5d5e5. So an exact match is tried first, then the available id that this
    is a prefix of - never the other way round for short ids, which is how a
    document called "a" would otherwise claim every citation beginning with an
    'a'."""
    if cited in available:
        return cited
    if len(cited) >= MIN_PREFIX:
        for doc_id in sorted(available):
            if doc_id.startswith(cited):
                return doc_id
    # the reverse: the model wrote more than the id. Rare, and only trusted
    # when the id itself is long enough for the overlap to mean something.
    for doc_id in sorted(available):
        if len(doc_id) >= MIN_PREFIX and cited.startswith(doc_id):
            return doc_id
    return None


def cited_docs(text: str, evidence: list = None) -> set:
    """The document ids this answer claims to have used.

    Without evidence this is what the text literally says. With it, truncated
    ids are resolved onto the documents actually retrieved, so a citation the
    UI can turn into a link comes back as the full id.
    """
    text = text or ""
    raw = set(DOC_RE.findall(text)) | set(BARE_DOC_RE.findall(text))

    if not evidence:
        return raw

    available = {e.doc_id for e in evidence if e.doc_id}
    raw |= {h for h in HEX_WORD_RE.findall(text)
            if any(a.startswith(h.lower()) for a in available)}

    return {_resolve(c, available) or c for c in raw}


def classify(text: str, evidence: list) -> tuple:
    """-> (grounding, confidence). Both fall out of the same comparison."""
    available = {e.doc_id for e in evidence if e.doc_id}
    cited = cited_docs(text, evidence)

    if any(_resolve(c, available) is None for c in cited):
        # naming a document that was never in the context means the id came out
        # of the model, not out of retrieval
        return "unverified", "low"

    if not cited:
        return "general", "medium"

    # confidence tracks corroboration - how many distinct documents the
    # answer actually leaned on
    return "documents", "high" if len(cited) >= 2 else "medium"
