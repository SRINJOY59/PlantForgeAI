"""Deterministic denoise signals - the cheap, safe checks that run before
any LLM. These catch the noise that needs no judgment: nodes that are
document references miscaught as equipment, and labels that are obviously a
cause-mechanism or a flattened sentence rather than a clean failure mode."""

import re

# surface forms that look like tags but are really document/record ids:
# incident reports, work orders, inspection records, SOPs, datasheets
DOC_REF_RE = re.compile(r"^(IR|WO|INS|SOP|PD|IOM|DWG|PID)-?\d", re.I)

# ISO 14224 leans on cause/mechanism vs mode. A short lexicon is enough to
# flag the clearest mechanisms; the LLM handles the rest with this as a hint.
MECHANISM_WORDS = {
    "cavitation", "corrosion", "erosion", "fatigue", "fouling", "scaling",
    "blockage", "wear", "misalignment", "imbalance", "overload", "overheat",
    "contamination", "dead-head", "dead-headed",
}

CAUSAL_CONNECTIVES = ("leading to", "led to", "due to", "caused by",
                      "resulting in", "because of", "from")


def is_doc_reference(surface: str) -> bool:
    """A tag-shaped node that is actually a document id -> noise to prune."""
    return bool(DOC_REF_RE.match(surface.strip()))


def looks_like_mechanism(label: str) -> bool:
    words = re.split(r"[-\s]+", label.lower())
    return any(w in MECHANISM_WORDS for w in words)


def looks_like_sentence(label: str) -> bool:
    """A 'failure mode' that is really a flattened causal chain."""
    low = label.lower().replace("-", " ")
    if any(c in low for c in CAUSAL_CONNECTIVES):
        return True
    return len(label.split("-")) >= 5 or len(low.split()) >= 6
