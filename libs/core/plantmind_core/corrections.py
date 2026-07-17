"""The on-disk shape of a correction.

The gateway writes these and the extraction lane reads them back, which is
exactly the kind of pair that drifts apart. One module owns the format so
there is only ever one definition of it.

Markdown rather than json, because a correction is a document like any other:
it lands in the object store, it gets a doc_id, and when a future answer cites
it the evidence viewer shows an engineer a readable record of who said what
was wrong and when - not a serialised payload.
"""

import re
from dataclasses import dataclass, field

SUFFIX = ".correction.md"

_FIELD_RE = re.compile(r"^([a-z_]+):\s*(.*)$", re.MULTILINE)


@dataclass
class Correction:
    question: str
    answer: str
    correction: str
    author: str = ""
    date: str = ""
    cited_docs: list = field(default_factory=list)


def filename(correction_id: str) -> str:
    return f"correction-{correction_id}{SUFFIX}"


def render(c: Correction) -> bytes:
    return (
        "---\n"
        f"author: {c.author}\n"
        f"date: {c.date}\n"
        f"cited_docs: {', '.join(c.cited_docs)}\n"
        "---\n\n"
        "# Correction\n\n"
        "## Question asked\n\n"
        f"{c.question}\n\n"
        "## Answer given\n\n"
        f"{c.answer}\n\n"
        "## What is actually correct\n\n"
        f"{c.correction}\n"
    ).encode("utf-8")


def parse(text: str) -> Correction:
    header, body = _split(text)
    meta = dict(_FIELD_RE.findall(header))
    return Correction(
        question=_section(body, "Question asked"),
        answer=_section(body, "Answer given"),
        correction=_section(body, "What is actually correct"),
        author=meta.get("author", ""),
        date=meta.get("date", ""),
        cited_docs=[d.strip() for d in meta.get("cited_docs", "").split(",")
                    if d.strip()],
    )


def _split(text: str):
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[1], parts[2]
    return "", text


def _section(body: str, heading: str) -> str:
    """Everything under '## <heading>' up to the next heading. An engineer
    writing a correction will use blank lines and lists; only another heading
    ends a section."""
    match = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)",
                      body, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""
