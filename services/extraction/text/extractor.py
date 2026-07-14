from plantmind_core import tags
from plantmind_core.schemas import (
    CandidateEdge, CandidateNode, CandidateSubgraph, EdgeType, NodeType, Provenance,
)
from plantmind_core.telemetry import get_logger

from extraction.text.chunker import SectionChunker
from extraction.text.relations import (   # re-exported for callers/tests
    BatchFindings, FailureFinding, ProcedureFinding, RegulationFinding,
    RelationExtractor, ensure_tag_node,
)

log = get_logger("extraction.text")

EXTRACTOR_VERSION = "text-v2"

# template context gets most of the "contextual retrieval" win for free;
# an LLM-written document summary can replace it later without schema changes
CONTEXT_TEMPLATE = "From {filename}, section {section}: "


class TextExtractor:
    def __init__(self, llm, embedder, chunker=None):
        self._relations = RelationExtractor(llm)
        self._embedder = embedder
        self._chunker = chunker or SectionChunker()

    async def extract(self, doc_id: str, content_hash: str, filename: str,
                      text: str) -> CandidateSubgraph:
        sections = self._chunker.split(text)
        chunks = [c for s in sections for c in s.chunks]
        if not chunks:
            raise ValueError(f"{filename}: no extractable text")

        nodes = {("Document", doc_id): CandidateNode(
            type=NodeType.DOCUMENT, surface_form=doc_id,
            props={"filename": filename, "content_hash": content_hash})}
        edges = []

        self._section_layer(doc_id, sections, nodes, edges)
        await self._embed_layer(doc_id, filename, sections, nodes)
        known_tags = self._mention_pass(doc_id, text, nodes, edges)
        await self._relations.run(
            filename, chunks, known_tags, nodes, edges,
            make_prov=lambda c, conf: self._prov(doc_id, c.start, c.end, conf))

        return CandidateSubgraph(doc_id=doc_id, content_hash=content_hash,
                                 nodes=list(nodes.values()), edges=edges)

    # parent-child structure: chunk -> section -> document
    def _section_layer(self, doc_id, sections, nodes, edges):
        for section in sections:
            section_id = f"{doc_id}#sec{section.index}"
            nodes[("Section", section_id)] = CandidateNode(
                type=NodeType.SECTION, surface_form=section_id,
                props={"title": section.title,
                       "text": "\n\n".join(c.text for c in section.chunks),
                       "start": section.start, "end": section.end})
            edges.append(CandidateEdge(
                type=EdgeType.PART_OF, src=section_id, dst=doc_id,
                provenance=self._prov(doc_id, section.start, section.end, 1.0)))
            for chunk in section.chunks:
                edges.append(CandidateEdge(
                    type=EdgeType.PART_OF, src=f"{doc_id}#chunk{chunk.index}",
                    dst=section_id,
                    provenance=self._prov(doc_id, chunk.start, chunk.end, 1.0)))

    # contextual enrichment: embed context+text, store raw text for reading
    async def _embed_layer(self, doc_id, filename, sections, nodes):
        enriched, chunk_meta = [], []
        for section in sections:
            for chunk in section.chunks:
                context = CONTEXT_TEMPLATE.format(filename=filename,
                                                  section=section.title or "start")
                enriched.append(context + chunk.text)
                chunk_meta.append((chunk, section, context))

        embeddings = await self._embedder.embed(enriched)
        for (chunk, section, context), emb in zip(chunk_meta, embeddings):
            chunk_id = f"{doc_id}#chunk{chunk.index}"
            nodes[("Chunk", chunk_id)] = CandidateNode(
                type=NodeType.CHUNK, surface_form=chunk_id,
                props={"text": chunk.text, "context": context,
                       "section": section.title, "start": chunk.start,
                       "end": chunk.end, "embedding": emb})

    # deterministic layer: every tag-shaped string becomes a mention edge
    def _mention_pass(self, doc_id, text, nodes, edges):
        seen = set()
        for tag, start, end in tags.find_tags(text):
            ensure_tag_node(nodes, tag)
            if tag not in seen:            # one mention edge per tag per doc
                seen.add(tag)
                edges.append(CandidateEdge(
                    type=EdgeType.MENTIONED_IN, src=tag, dst=doc_id,
                    provenance=self._prov(doc_id, start, end, 1.0)))
        return sorted(seen)

    @staticmethod
    def _prov(doc_id, start, end, confidence):
        return Provenance(doc_id=doc_id, span=(start, end),
                          extractor_version=EXTRACTOR_VERSION,
                          confidence=confidence)


def main():
    """usage (from plantmind/services, needs OPENROUTER_API_KEY in ../.env):
    ../.venv/Scripts/python -m extraction.text.extractor ../data/samples/sop_pump_seal_replacement.md"""
    import asyncio
    import sys
    from pathlib import Path

    from plantmind_core.devtools import find_file, summarize
    from plantmind_core.llm import get_embedder, get_llm

    extractor = TextExtractor(get_llm(), get_embedder())
    for arg in sys.argv[1:]:
        path = find_file(arg)
        csg = asyncio.run(extractor.extract(
            "smoke-" + path.stem, "smoke-hash", path.name,
            path.read_text(encoding="utf-8")))
        summarize(csg)


if __name__ == "__main__":
    main()
