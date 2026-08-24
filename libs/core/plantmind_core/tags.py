"""ISA-5.1 style equipment/instrument tag handling. Used by the extractors
to find tags in text and by the resolver to canonicalise them."""

import re

# The trailing letter is a tag SUFFIX (the A of P-101A), and it may be
# separated by spaces so that "P 101 A" still reads as one tag. That spacing
# tolerance is what made the old form
#     \b([A-Za-z]{1,4})[-\s]?(\d{2,5})\s*([A-Za-z]?)\b
# reach across a word boundary and eat the first letter of the NEXT tag:
#     "unit 200 P-101A"   -> UNIT-200P   (and P-101A lost entirely)
#     "WO 4471 K-301"     -> WO-4471K    (and K-301 lost)
#     "V-210 V-211"       -> V-210V      (and V-211 lost)
# Phrasings like those are everywhere in work orders and incident reports, so
# this was inventing phantom equipment and dropping real tags throughout
# ingestion. The lookahead declines the suffix when the letter is followed by
# its own digits - i.e. when it is starting a tag rather than ending one.
TAG_RE = re.compile(
    r"\b([A-Za-z]{1,4})[-\s]?(\d{2,5})(?:\s*([A-Za-z])(?![-\s]?\d{2,5}))?\b")

# ISA instrument letter codes: first letter = measured variable,
# rest = function. Anything else (P, K, V, T, E...) is plant equipment.
INSTRUMENT_PREFIXES = {
    "PI", "PT", "PIC", "PSV", "PCV",
    "TI", "TT", "TIC", "TCV",
    "FI", "FT", "FIC", "FCV",
    "LI", "LT", "LIC", "LCV",
    "AI", "AT", "XV", "HS",
}


def find_tags(text: str):
    """Yield (tag, start, end) for every tag-shaped mention."""
    for m in TAG_RE.finditer(text):
        yield normalize(m.group(0)), m.start(), m.end()


def normalize(raw: str) -> str:
    """'p 101 a', 'P-101a', 'P101A' -> 'P-101A'"""
    cleaned = re.sub(r"[\s_]+", "", raw.upper().replace("&", ""))
    m = re.fullmatch(r"([A-Z]{1,4})-?(\d{2,5})-?([A-Z]?)", cleaned)
    if not m:
        return raw.strip().upper()
    prefix, number, suffix = m.groups()
    return f"{prefix}-{number}{suffix}"


def looks_like_tag(raw: str) -> bool:
    cleaned = re.sub(r"[\s_]+", "", raw.upper())
    return re.fullmatch(r"([A-Z]{1,4})-?(\d{2,5})-?([A-Z]?)", cleaned) is not None


def is_instrument(tag: str) -> bool:
    return tag.split("-", 1)[0] in INSTRUMENT_PREFIXES
