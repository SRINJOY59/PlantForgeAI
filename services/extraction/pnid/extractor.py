from typing import Literal

from pydantic import BaseModel

from plantmind_core import tags
from plantmind_core.schemas import (
    CandidateEdge, CandidateNode, CandidateSubgraph, EdgeType, NodeType, Provenance,
)
from plantmind_core.telemetry import get_logger

from extraction.pnid.raster import to_png_b64

log = get_logger("extraction.pnid")

EXTRACTOR_VERSION = "pnid-v1"


class Component(BaseModel):
    tag: str
    kind: Literal["equipment", "instrument", "valve", "line", "other"] = "equipment"
    description: str = ""
    bbox: tuple[float, float, float, float] | None = None


class ComponentList(BaseModel):
    components: list[Component]


class Connection(BaseModel):
    from_tag: str
    to_tag: str
    direction: Literal["forward", "bidirectional", "unknown"] = "forward"


class ConnectionList(BaseModel):
    connections: list[Connection]


PASS1 = """This is a piping and instrumentation diagram (P&ID).
List every tagged component you can identify: equipment (pumps, vessels,
exchangers, compressors, tanks), instruments (circles with letter-number
labels like PI-102), valves (including relief valves like PSV-204), and
line numbers (e.g. 4"-CS-150).
Report tags exactly as written on the drawing.
If bounding box coordinates are provided in the input, include them in the bbox field."""

PASS2 = """Same P&ID. These components were identified: {tag_list}

Now trace the process lines. List every direct connection between two of
those tags. Determine flow direction (forward, bidirectional, unknown) based on arrowheads.
Only report connections you can actually follow along a drawn line."""


class PnidExtractor:
    """Two-pass VLM extraction: components first, then connectivity over the
    confirmed component list. ISA tag grammar filters hallucinated tags;
    pass-2 endpoints must come from pass-1."""

    def __init__(self, llm):
        self._llm = llm

    async def extract(self, doc_id: str, content_hash: str, filename: str,
                      data: bytes) -> CandidateSubgraph:
        if filename.lower().endswith(".svg"):
            # vector source is richer than any raster of it - send the XML
            doc_content = [{"role": "user", "content":
                            PASS1 + "\n\nSVG source:\n" + data.decode("utf-8", "replace")}]
            comps = await self._llm.structured(doc_content, ComponentList)
            pass2_msgs = [{"role": "user", "content":
                           PASS2.format(tag_list=self._tag_list(comps)) +
                           "\n\nSVG source:\n" + data.decode("utf-8", "replace")}]
            conns = await self._llm.structured(pass2_msgs, ConnectionList)
        elif filename.lower().endswith(".pdf"):
            import fitz
            import re
            
            # Layer 1: Vector Path for PDFs to get deterministic text & bboxes
            doc = fitz.open(stream=data, filetype="pdf")
            blocks = []
            for page in doc:
                text_blocks = page.get_text("blocks")
                for b in text_blocks:
                    x0, y0, x1, y1, text, block_no, block_type = b
                    text = text.strip().replace("\n", " ")
                    if text:
                        blocks.append(f"Text: '{text}', BBox: [{x0:.1f}, {y0:.1f}, {x1:.1f}, {y1:.1f}]")
            doc.close()
            
            vector_context = "\n".join(blocks)
            doc_content = [{"role": "user", "content":
                            PASS1 + "\n\nExtracted PDF Vector Text Blocks:\n" + vector_context}]
            comps = await self._llm.structured(doc_content, ComponentList)
            
            # Fallback raster for pass 2 to trace lines visually
            images = to_png_b64(data, filename)
            conns = await self._llm.vision_structured(
                PASS2.format(tag_list=self._tag_list(comps)), images, ConnectionList)
        else:
            images = to_png_b64(data, filename)
            comps = await self._llm.vision_structured(PASS1, images, ComponentList)
            conns = await self._llm.vision_structured(
                PASS2.format(tag_list=self._tag_list(comps)), images, ConnectionList)

        return self._build(doc_id, content_hash, filename, comps, conns)

    @staticmethod
    def _tag_list(comps: ComponentList) -> str:
        return ", ".join(c.tag for c in comps.components)

    def _build(self, doc_id, content_hash, filename,
               comps: ComponentList, conns: ConnectionList) -> CandidateSubgraph:
        nodes = {}
        edges = []
        prov = Provenance(doc_id=doc_id, page=1,
                          extractor_version=EXTRACTOR_VERSION, confidence=0.85)

        known = set()
        for comp in comps.components:
            if not tags.looks_like_tag(comp.tag):
                log.warning("dropped non-grammatical tag", tag=comp.tag)
                continue
            tag = tags.normalize(comp.tag)
            known.add(tag)
            node_type = NodeType.INSTRUMENT if (
                comp.kind == "instrument" or tags.is_instrument(tag)
            ) else NodeType.EQUIPMENT
            props = {"kind": comp.kind}
            if comp.description:
                props["description"] = comp.description
            if comp.bbox:
                props["bbox"] = comp.bbox
            nodes[tag] = CandidateNode(type=node_type, surface_form=tag,
                                       props=props)
            edges.append(CandidateEdge(type=EdgeType.MENTIONED_IN,
                                       src=tag, dst=doc_id, provenance=prov))

        for conn in conns.connections:
            src, dst = tags.normalize(conn.from_tag), tags.normalize(conn.to_tag)
            if src not in known or dst not in known or src == dst:
                log.warning("dropped connection with unknown endpoint",
                            src=conn.from_tag, dst=conn.to_tag)
                continue
            edges.append(CandidateEdge(type=EdgeType.CONNECTED_TO,
                                       src=src, dst=dst, provenance=prov,
                                       props={"direction": conn.direction}))

        doc_node = CandidateNode(type=NodeType.DOCUMENT, surface_form=doc_id,
                                 props={"filename": filename,
                                        "content_hash": content_hash})
        return CandidateSubgraph(doc_id=doc_id, content_hash=content_hash,
                                 nodes=[*nodes.values(), doc_node], edges=edges)


def main():
    """usage (from plantmind/services, needs OPENROUTER_API_KEY in ../.env):
    ../.venv/Scripts/python -m extraction.pnid.extractor ../data/samples/pnid_unit100.svg"""
    import asyncio
    import sys
    from pathlib import Path

    from plantmind_core.devtools import find_file, summarize
    from plantmind_core.llm import get_llm

    extractor = PnidExtractor(get_llm())
    for arg in sys.argv[1:]:
        path = find_file(arg)
        csg = asyncio.run(extractor.extract(
            "smoke-" + path.stem, "smoke-hash", path.name, path.read_bytes()))
        summarize(csg)


if __name__ == "__main__":
    main()
