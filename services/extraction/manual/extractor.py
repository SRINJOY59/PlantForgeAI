"""Long-document lane (OEM manuals, handbooks). A manual is a tree, not a
long SOP: the outline becomes nested Section nodes, chunks carry their
chapter path as embedding context, and provenance cites pages."""

import re

from pydantic import BaseModel, Field

from plantmind_core import tags
from plantmind_core.llm import Tier
from plantmind_core.schemas import (
    CandidateEdge, CandidateNode, CandidateSubgraph, EdgeType, NodeType, Provenance,
)
from plantmind_core.telemetry import get_logger

from extraction.text.relations import RelationExtractor, ensure_tag_node

log = get_logger("extraction.manual")

EXTRACTOR_VERSION = "manual-v1"
MAX_CHUNK_CHARS = 2400

HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+\S")


class OutlineEntry(BaseModel):
    title: str
    level: int = Field(default=1, ge=1, le=4)
    start_page: int = Field(ge=1)


class Outline(BaseModel):
    entries: list[OutlineEntry]


OUTLINE_PROMPT = """These are heading-candidate lines from an equipment
manual ({filename}, {n_pages} pages), with the page each line appears on.
Reconstruct the document outline: real structural headings only (chapters
and sections), with level 1 for chapters, 2 for sections, 3 for
subsections. Ignore table-of-contents entries themselves, list items,
figure captions and page furniture.

{candidates}"""


class ManualExtractor:
    def __init__(self, llm, embedder):
        self._llm = llm
        self._embedder = embedder
        self._relations = RelationExtractor(llm)

    async def extract(self, doc_id: str, content_hash: str, filename: str,
                      pages: list[str]) -> CandidateSubgraph:
        pages = strip_page_furniture(pages)
        if not any(p.strip() for p in pages):
            raise ValueError(f"{filename}: no extractable text")

        outline = await self._outline(filename, pages)

        nodes = {("Document", doc_id): CandidateNode(
            type=NodeType.DOCUMENT, surface_form=doc_id,
            props={"filename": filename, "content_hash": content_hash,
                   "pages": len(pages)})}
        edges = []

        chunks = self._build_tree(doc_id, filename, pages, outline, nodes, edges)
        await self._embed(doc_id, nodes, chunks)
        known_tags = self._mention_pass(doc_id, pages, nodes, edges)
        await self._relations.run(
            filename, [c for c, _ in chunks], known_tags, nodes, edges,
            make_prov=lambda c, conf: Provenance(
                doc_id=doc_id, page=c.page, extractor_version=EXTRACTOR_VERSION,
                confidence=conf))

        return CandidateSubgraph(doc_id=doc_id, content_hash=content_hash,
                                 nodes=list(nodes.values()), edges=edges)

    async def _outline(self, filename, pages) -> list[OutlineEntry]:
        candidates = []
        for page_no, page in enumerate(pages, start=1):
            for line in page.splitlines():
                if HEADING_RE.match(line) and len(line.strip()) < 90:
                    candidates.append(f"p{page_no}: {line.strip()}")
        candidates = candidates[:200]

        entries = []
        if candidates and self._llm is not None:
            try:
                outline = await self._llm.structured(
                    [{"role": "user", "content": OUTLINE_PROMPT.format(
                        filename=filename, n_pages=len(pages),
                        candidates="\n".join(candidates))}],
                    Outline, tier=Tier.CHEAP)
                entries = [e for e in outline.entries
                           if 1 <= e.start_page <= len(pages)]
                entries.sort(key=lambda e: e.start_page)
            except Exception as e:
                log.warning("outline inference failed, using heading regex",
                            error=str(e)[:200])
        if not entries:
            entries = self._regex_outline(pages)
        if not entries:
            entries = [OutlineEntry(title="Manual", level=1, start_page=1)]
        return entries

    @staticmethod
    def _regex_outline(pages) -> list[OutlineEntry]:
        entries = []
        for page_no, page in enumerate(pages, start=1):
            for line in page.splitlines():
                m = HEADING_RE.match(line)
                if m and len(line.strip()) < 90:
                    level = min(m.group(1).count(".") + 1, 4)
                    entries.append(OutlineEntry(
                        title=line.strip(), level=level, start_page=page_no))
        return entries

    def _build_tree(self, doc_id, filename, pages, entries, nodes, edges):
        """Nested Section nodes; each entry owns the pages from its start to
        the next entry's start. Returns [(chunk, section_id)]."""
        chunks = []
        stack = []          # [(level, section_id, title)]
        for i, entry in enumerate(entries):
            section_id = f"{doc_id}#sec{i}"
            while stack and stack[-1][0] >= entry.level:
                stack.pop()
            parent_id = stack[-1][1] if stack else doc_id
            path = [s[2] for s in stack] + [entry.title]

            end_page = entries[i + 1].start_page - 1 if i + 1 < len(entries) \
                else len(pages)
            end_page = max(end_page, entry.start_page)
            body = "\n".join(pages[entry.start_page - 1:end_page])

            nodes[("Section", section_id)] = CandidateNode(
                type=NodeType.SECTION, surface_form=section_id,
                props={"title": entry.title, "path": " > ".join(path),
                       "page_start": entry.start_page, "page_end": end_page,
                       "text": body.strip()})
            edges.append(CandidateEdge(
                type=EdgeType.PART_OF, src=section_id, dst=parent_id,
                provenance=self._page_prov(doc_id, entry.start_page)))
            stack.append((entry.level, section_id, entry.title))

            context = f"From {filename}, {' > '.join(path)}: "
            for text in _pack(body, MAX_CHUNK_CHARS):
                chunk = _ManualChunk(index=len(chunks), text=text,
                                     page=entry.start_page, context=context)
                chunks.append((chunk, section_id))
                edges.append(CandidateEdge(
                    type=EdgeType.PART_OF, src=f"{doc_id}#chunk{chunk.index}",
                    dst=section_id,
                    provenance=self._page_prov(doc_id, chunk.page)))
        return chunks

    async def _embed(self, doc_id, nodes, chunks):
        embeddings = await self._embedder.embed(
            [c.context + c.text for c, _ in chunks])
        for (chunk, _), emb in zip(chunks, embeddings):
            chunk_id = f"{doc_id}#chunk{chunk.index}"
            nodes[("Chunk", chunk_id)] = CandidateNode(
                type=NodeType.CHUNK, surface_form=chunk_id,
                props={"text": chunk.text, "context": chunk.context,
                       "page": chunk.page, "embedding": emb})

    def _mention_pass(self, doc_id, pages, nodes, edges):
        seen = set()
        for page_no, page in enumerate(pages, start=1):
            for tag, _, _ in tags.find_tags(page):
                ensure_tag_node(nodes, tag)
                if tag not in seen:
                    seen.add(tag)
                    edges.append(CandidateEdge(
                        type=EdgeType.MENTIONED_IN, src=tag, dst=doc_id,
                        provenance=self._page_prov(doc_id, page_no)))
        return sorted(seen)

    @staticmethod
    def _page_prov(doc_id, page):
        return Provenance(doc_id=doc_id, page=page,
                          extractor_version=EXTRACTOR_VERSION, confidence=1.0)


class _ManualChunk:
    def __init__(self, index, text, page, context):
        self.index = index
        self.text = text
        self.page = page
        self.context = context


def strip_page_furniture(pages: list[str]) -> list[str]:
    """Remove headers/footers: lines recurring at page tops/bottoms on most
    pages (company name, doc number, 'Page N of M')."""
    if len(pages) < 4:
        return pages
    from collections import Counter
    counter = Counter()
    for page in pages:
        lines = [l.strip() for l in page.splitlines() if l.strip()]
        for line in set(lines[:2] + lines[-2:]):
            counter[re.sub(r"\d+", "#", line)] += 1

    furniture = {pattern for pattern, n in counter.items()
                 if n >= max(4, int(0.6 * len(pages)))}
    if not furniture:
        return pages
    cleaned = []
    for page in pages:
        kept = [l for l in page.splitlines()
                if re.sub(r"\d+", "#", l.strip()) not in furniture]
        cleaned.append("\n".join(kept))
    return cleaned


def _pack(text: str, max_chars: int) -> list[str]:
    """Paragraph-packed pieces, never cutting mid-paragraph."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces, buf, size = [], [], 0
    for para in paras:
        if buf and size + len(para) > max_chars:
            pieces.append("\n\n".join(buf))
            buf, size = [], 0
        buf.append(para)
        size += len(para)
    if buf:
        pieces.append("\n\n".join(buf))
    return pieces


def main():
    """usage (from plantmind/services, needs OPENROUTER_API_KEY in ../.env):
    ../.venv/Scripts/python -m extraction.manual.extractor path/to/manual.pdf"""
    import asyncio
    import sys
    from pathlib import Path

    from plantmind_core.devtools import find_file, summarize
    from plantmind_core.llm import get_embedder, get_llm

    from extraction.manual.pdfio import read_pdf_pages

    extractor = ManualExtractor(get_llm(), get_embedder())
    for arg in sys.argv[1:]:
        path = find_file(arg)
        pages = read_pdf_pages(path.read_bytes())
        print(f"{path.name}: {len(pages)} pages")
        csg = asyncio.run(extractor.extract(
            "smoke-" + path.stem, "smoke-hash", path.name, pages))
        summarize(csg)


if __name__ == "__main__":
    main()
