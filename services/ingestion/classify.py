import re
from enum import Enum

from plantmind_core.queues import Routes
from plantmind_core.telemetry import get_logger

log = get_logger("ingestion.classify")


class DocKind(str, Enum):
    TABLE = "table"      # structured rows: work orders, inspection records
    PNID = "pnid"        # engineering drawings
    TEXT = "text"        # SOPs, incident reports, short prose
    MANUAL = "manual"    # long structured documents (OEM manuals, handbooks)
    EMAIL = "email"
    IMAGE = "image"      # standalone images: charts, nameplates, scans


ROUTE_FOR = {
    DocKind.TABLE: Routes.parse_workorder,
    DocKind.PNID: Routes.extract_pnid,
    DocKind.TEXT: Routes.extract_text,
    DocKind.MANUAL: Routes.extract_manual,
    DocKind.EMAIL: Routes.extract_email,
    DocKind.IMAGE: Routes.extract_image,
}

DRAWING_HINTS = ("pnid", "p&id", "pid-", "-pid", "dwg", "drawing")
IMAGE_EXTS = ("png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff")
MAIL_HEADER_RE = re.compile(r"^(From|To|Subject|Received|Return-Path|Date):",
                            re.MULTILINE)
MANUAL_MIN_PAGES = 16


class Classifier:
    """Rules decide the easy ~80%. Whatever the rules can't place goes to the
    llm_fallback if one is wired in, otherwise defaults to TEXT — the text
    pipeline is the safest place for a mystery document."""

    def __init__(self, llm_fallback=None):
        self._llm_fallback = llm_fallback

    def classify(self, filename: str, sniff: str, data: bytes = None) -> DocKind:
        name = filename.lower()
        ext = name.rsplit(".", 1)[-1] if "." in name else ""

        if ext in ("csv", "tsv", "xlsx", "xls", "xlsm"):
            return DocKind.TABLE
        if ext in ("eml", "msg") or (ext == "" and MAIL_HEADER_RE.search(sniff)):
            return DocKind.EMAIL
        if ext == "svg":
            return DocKind.PNID
        if any(hint in name for hint in DRAWING_HINTS):
            return DocKind.PNID
        if ext in IMAGE_EXTS:
            return DocKind.IMAGE
        if ext in ("md", "txt", "docx", "doc", "html"):
            return DocKind.TEXT
        if ext == "pdf":
            # a text-layer pdf sniffs readable words; a pure scan/drawing doesn't
            if len(sniff.split()) > 30:
                return DocKind.MANUAL if _pdf_pages(data) >= MANUAL_MIN_PAGES \
                    else DocKind.TEXT
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


def _pdf_pages(data: bytes) -> int:
    if not data:
        return 0
    return len(re.findall(rb"/Type\s*/Page\b", data))


def main():
    """usage (from plantmind/services):
    ../.venv/Scripts/python -m ingestion.classify ../data/samples/*"""
    import sys

    from plantmind_core.devtools import find_file

    classifier = Classifier()          # rules only, no tokens
    for arg in sys.argv[1:]:
        path = find_file(arg)
        data = path.read_bytes()
        sniff = data[:2048].decode("utf-8", errors="ignore")
        kind = classifier.classify(path.name, sniff, data)
        print(f"{path.name:40s} -> {kind.value:8s} ({ROUTE_FOR[kind].queue})")


if __name__ == "__main__":
    main()
