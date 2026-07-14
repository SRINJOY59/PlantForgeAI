"""Email lane. Parses the message, strips quoted replies (facts in quotes
belong to the original mail, which gets ingested separately - extracting
them twice would double-count evidence), then reuses the text pipeline on
subject + cleaned body. Sender/recipients become Person nodes."""

import email
import email.policy
import re

from plantmind_core.schemas import CandidateEdge, CandidateNode, EdgeType, \
    NodeType, Provenance

EXTRACTOR_VERSION = "email-v1"

QUOTE_MARKERS = (
    re.compile(r"^\s*>"),                                  # > quoted line
    re.compile(r"^On .{5,80} wrote:\s*$"),                 # reply header
    re.compile(r"^-{3,}\s*Original Message\s*-{3,}", re.I),
    re.compile(r"^From:.*$"),                              # forwarded block
)


class EmailExtractor:
    def __init__(self, text_extractor):
        self._text = text_extractor

    async def extract(self, doc_id, content_hash, filename, data: bytes):
        msg = email.message_from_bytes(data, policy=email.policy.default)
        subject = msg.get("Subject", "").strip()
        body = _plain_body(msg)
        cleaned = _strip_quotes(body)

        csg = await self._text.extract(
            doc_id, content_hash, filename,
            f"# {subject}\n\n{cleaned}" if subject else cleaned)

        doc = next(n for n in csg.nodes if n.type == NodeType.DOCUMENT)
        doc.props.update({"subject": subject,
                          "from": msg.get("From", ""),
                          "to": msg.get("To", ""),
                          "date": msg.get("Date", "")})

        prov = Provenance(doc_id=doc_id, extractor_version=EXTRACTOR_VERSION,
                          confidence=1.0)
        for role in ("From", "To", "Cc"):
            for name, addr in _people(msg.get(role, "")):
                surface = name or addr
                if not any(n.type == NodeType.PERSON and n.surface_form == surface
                           for n in csg.nodes):
                    csg.nodes.append(CandidateNode(
                        type=NodeType.PERSON, surface_form=surface,
                        props={"email": addr} if addr else {}))
                csg.edges.append(CandidateEdge(
                    type=EdgeType.MENTIONED_IN, src=surface, dst=doc_id,
                    provenance=prov, props={"role": role.lower()}))
        return csg


def _plain_body(msg) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    content = part.get_content()
    if part.get_content_type() == "text/html":
        content = re.sub(r"<[^>]+>", " ", content)
    return content


def _strip_quotes(body: str) -> str:
    kept = []
    for line in body.splitlines():
        if any(marker.match(line) for marker in QUOTE_MARKERS):
            break                      # everything below is quoted history
        kept.append(line)
    return "\n".join(kept).strip()


def _people(header: str):
    for part in header.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>$', part)
        if m:
            yield m.group(1).strip(), m.group(2).strip()
        elif "@" in part:
            yield "", part


def main():
    """usage (from plantmind/services, needs OPENROUTER_API_KEY in ../.env):
    ../.venv/Scripts/python -m extraction.mail.extractor path/to/message.eml"""
    import asyncio
    import sys
    from pathlib import Path

    from plantmind_core.devtools import find_file, summarize
    from plantmind_core.llm import get_embedder, get_llm

    from extraction.text.extractor import TextExtractor

    extractor = EmailExtractor(TextExtractor(get_llm(), get_embedder()))
    for arg in sys.argv[1:]:
        path = find_file(arg)
        csg = asyncio.run(extractor.extract(
            "smoke-" + path.stem, "smoke-hash", path.name, path.read_bytes()))
        summarize(csg)


if __name__ == "__main__":
    main()
