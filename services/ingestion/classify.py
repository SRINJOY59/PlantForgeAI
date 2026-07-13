from enum import Enum

from plantmind_core.queues import Routes
from plantmind_core.telemetry import get_logger

log = get_logger("ingestion.classify")


class DocKind(str, Enum):
    TABLE = "table"    # structured rows: work orders, inspection records
    PNID = "pnid"      # engineering drawings
    TEXT = "text"      # SOPs, incident reports, manuals, email


ROUTE_FOR = {
    DocKind.TABLE: Routes.parse_workorder,
    DocKind.PNID: Routes.extract_pnid,
    DocKind.TEXT: Routes.extract_text,
}

DRAWING_HINTS = ("pnid", "p&id", "pid-", "-pid", "dwg", "drawing")


class Classifier:
    """Rules decide the easy ~80%. Whatever the rules can't place goes to the
    llm_fallback if one is wired in, otherwise defaults to TEXT — the text
    pipeline is the safest place for a mystery document."""

    def __init__(self, llm_fallback=None):
        self._llm_fallback = llm_fallback

    def classify(self, filename: str, sniff: str) -> DocKind:
        name = filename.lower()
        ext = name.rsplit(".", 1)[-1] if "." in name else ""

        if ext in ("csv", "tsv", "xlsx", "xls"):
            return DocKind.TABLE
        if ext == "svg":
            return DocKind.PNID
        if any(hint in name for hint in DRAWING_HINTS):
            return DocKind.PNID
        if ext in ("md", "txt", "docx", "doc", "eml", "html"):
            return DocKind.TEXT
        if ext == "pdf":
            # a text-layer pdf sniffs readable words; a pure scan/drawing doesn't
            if len(sniff.split()) > 30:
                return DocKind.TEXT
            return self._ask_fallback(filename, sniff)
        return self._ask_fallback(filename, sniff)

    def _ask_fallback(self, filename: str, sniff: str) -> DocKind:
        if self._llm_fallback is None:
            log.warning("no rule matched, defaulting to text", filename=filename)
            return DocKind.TEXT
        try:
            verdict = self._llm_fallback(filename, sniff)
            return DocKind(verdict)
        except Exception as e:
            log.warning("llm fallback failed, defaulting to text",
                        filename=filename, error=str(e)[:200])
            return DocKind.TEXT
