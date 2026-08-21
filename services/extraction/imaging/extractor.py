"""Standalone-image lane. One vision call decides what the image IS, then
the right specialist runs: charts become searchable data summaries,
nameplates become equipment properties, drawings go to the P&ID extractor,
photographed/scanned documents get transcribed into the text pipeline."""

from typing import Literal

from pydantic import BaseModel

from plantmind_core import tags
from plantmind_core.schemas import (
    CandidateEdge, CandidateNode, CandidateSubgraph, EdgeType, NodeType, Provenance,
)
from plantmind_core.telemetry import get_logger

from extraction.pnid.raster import to_png_b64

log = get_logger("extraction.imaging")

EXTRACTOR_VERSION = "image-v1"


class ImageVerdict(BaseModel):
    kind: Literal["chart", "nameplate", "drawing", "document", "other"]


class DataPoint(BaseModel):
    x: str
    y: str


class Series(BaseModel):
    name: str
    points: list[DataPoint] = []


class ChartReading(BaseModel):
    chart_type: Literal["line", "bar", "scatter", "pie", "other"] = "other"
    title: str = ""
    x_axis: str = ""
    y_axis: str = ""
    series: list[Series] = []
    summary: str = ""       # the trend in plain words, 2-3 sentences


class Nameplate(BaseModel):
    equipment_tag: str = ""
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""
    ratings: list[str] = []


CLASSIFY_PROMPT = """Classify this industrial image as exactly one kind:
chart (graph/trend plot), nameplate (equipment nameplate/label photo),
drawing (P&ID or engineering diagram), document (photo or scan of a text
document), other."""

# Both specialist prompts cap their own output. A trend plot has effectively
# unbounded readable points and a weathered nameplate invites the model into a
# repetition loop; either one runs past the token budget and comes back as JSON
# that stops mid-string, which is a parse error rather than a bad reading. The
# graph wants the SHAPE of the curve and the plate's identifiers, so bounding
# the ask costs nothing we store.
CHART_PROMPT = """Read this chart. Extract its type, title, axes, its series
with their data points, and a 2-3 sentence summary of the trend in plain
engineering language, naming equipment tags if the chart references any.

Limits - obey them exactly: at most 6 series, at most 40 points per series
(sample evenly across the x-axis if the chart has more, keeping the first and
last), and at most 3 sentences of summary. Never repeat a point or a label."""

NAMEPLATE_PROMPT = """Read this equipment nameplate photo. Extract the
equipment tag if visible, manufacturer, model, serial number, and rating
lines exactly as printed.

Limits - obey them exactly: every field is a single short line (under 80
characters), and at most 12 rating lines. Transcribe each line once; if a
line is unreadable, leave it out rather than guessing or repeating."""

OCR_PROMPT = """Transcribe ALL readable text in this document image,
preserving structure with markdown headings where the layout implies them."""


class ImageLane:
    def __init__(self, llm, embedder, pnid_extractor, text_extractor):
        self._llm = llm
        self._embedder = embedder
        self._pnid = pnid_extractor
        self._text = text_extractor

    async def extract(self, doc_id, content_hash, filename,
                      data: bytes) -> CandidateSubgraph:
        images = to_png_b64(data, filename)
        verdict = await self._llm.vision_structured(CLASSIFY_PROMPT, images,
                                                    ImageVerdict)
        log.info("image classified", doc_id=doc_id, kind=verdict.kind)

        if verdict.kind == "drawing":
            return await self._pnid.extract(doc_id, content_hash, filename, data)
        if verdict.kind == "chart":
            return await self._specialist_or_ocr(
                self._chart, verdict.kind, doc_id, content_hash, filename, images)
        if verdict.kind == "nameplate":
            return await self._specialist_or_ocr(
                self._nameplate, verdict.kind, doc_id, content_hash, filename,
                images)
        # document / other: transcribe, then the full text pipeline applies
        return await self._ocr(doc_id, content_hash, filename, images)

    async def _specialist_or_ocr(self, specialist, kind, doc_id, content_hash,
                                 filename, images):
        """Run the specialist reader, falling back to transcription if it
        cannot produce a valid reading.

        The specialists ask for a strict shape (ChartReading, Nameplate) and a
        vision model that overruns its token budget answers with JSON that
        stops mid-string. That used to raise out of the lane, which releases
        the document's hash claim and retries the whole thing - and the retries
        overrun in the same place, so the image ended in the DLQ having put
        NOTHING in the graph. A photograph we could not parse into a schema is
        still a photograph full of readable text, so we take the plain OCR path
        instead: the document lands, its tags get linked, and the only loss is
        the structured series/ratings.
        """
        try:
            return await specialist(doc_id, content_hash, filename, images)
        except Exception as e:
            log.warning("specialist read failed, falling back to ocr",
                        doc_id=doc_id, filename=filename, kind=kind,
                        error_type=type(e).__name__, error=str(e)[:200])
            return await self._ocr(doc_id, content_hash, filename, images)

    async def _ocr(self, doc_id, content_hash, filename, images):
        transcript = await self._llm.vision(OCR_PROMPT, images)
        return await self._text.extract(doc_id, content_hash, filename,
                                        transcript)

    async def _chart(self, doc_id, content_hash, filename, images):
        reading = await self._llm.vision_structured(CHART_PROMPT, images,
                                                    ChartReading)
        searchable = " ".join(filter(None, [
            reading.title, reading.summary,
            *(s.name for s in reading.series)]))
        (embedding,) = await self._embedder.embed([searchable]) or [[]]

        nodes, edges = self._doc_shell(doc_id, content_hash, filename)
        chunk_id = f"{doc_id}#chart0"
        nodes.append(CandidateNode(
            type=NodeType.CHUNK, surface_form=chunk_id,
            props={"kind": "chart", "chart_type": reading.chart_type,
                   "title": reading.title, "x_axis": reading.x_axis,
                   "y_axis": reading.y_axis,
                   "series": [s.model_dump() for s in reading.series],
                   "text": searchable, "embedding": embedding}))
        edges.append(CandidateEdge(type=EdgeType.PART_OF, src=chunk_id,
                                   dst=doc_id, provenance=self._prov(doc_id)))
        self._mentions(doc_id, searchable, nodes, edges)
        return CandidateSubgraph(doc_id=doc_id, content_hash=content_hash,
                                 nodes=nodes, edges=edges)

    async def _nameplate(self, doc_id, content_hash, filename, images):
        plate = await self._llm.vision_structured(NAMEPLATE_PROMPT, images,
                                                  Nameplate)
        nodes, edges = self._doc_shell(doc_id, content_hash, filename)

        if plate.equipment_tag and tags.looks_like_tag(plate.equipment_tag):
            tag = tags.normalize(plate.equipment_tag)
            props = {k: v for k, v in {
                "manufacturer": plate.manufacturer, "model": plate.model,
                "serial_number": plate.serial_number,
                "ratings": plate.ratings}.items() if v}
            node_type = NodeType.INSTRUMENT if tags.is_instrument(tag) \
                else NodeType.EQUIPMENT
            nodes.append(CandidateNode(type=node_type, surface_form=tag,
                                       props=props))
            edges.append(CandidateEdge(type=EdgeType.MENTIONED_IN, src=tag,
                                       dst=doc_id, provenance=self._prov(doc_id)))
        else:
            log.warning("nameplate without readable tag", doc_id=doc_id,
                        raw_tag=plate.equipment_tag)
        return CandidateSubgraph(doc_id=doc_id, content_hash=content_hash,
                                 nodes=nodes, edges=edges)

    def _mentions(self, doc_id, text, nodes, edges):
        seen = set()
        for tag, _, _ in tags.find_tags(text):
            if tag in seen:
                continue
            seen.add(tag)
            node_type = NodeType.INSTRUMENT if tags.is_instrument(tag) \
                else NodeType.EQUIPMENT
            nodes.append(CandidateNode(type=node_type, surface_form=tag))
            edges.append(CandidateEdge(type=EdgeType.MENTIONED_IN, src=tag,
                                       dst=doc_id, provenance=self._prov(doc_id)))

    @staticmethod
    def _doc_shell(doc_id, content_hash, filename):
        return [CandidateNode(type=NodeType.DOCUMENT, surface_form=doc_id,
                              props={"filename": filename,
                                     "content_hash": content_hash})], []

    @staticmethod
    def _prov(doc_id):
        return Provenance(doc_id=doc_id, page=1,
                          extractor_version=EXTRACTOR_VERSION, confidence=0.85)


def main():
    """usage (from plantmind/services, needs OPENROUTER_API_KEY in ../.env):
    ../.venv/Scripts/python -m extraction.imaging.extractor path/to/photo.jpg"""
    import asyncio
    import sys
    from pathlib import Path

    from plantmind_core.devtools import find_file, summarize
    from plantmind_core.llm import get_embedder, get_llm

    from extraction.pnid.extractor import PnidExtractor
    from extraction.text.extractor import TextExtractor

    llm, embedder = get_llm(), get_embedder()
    lane = ImageLane(llm, embedder, PnidExtractor(llm),
                     TextExtractor(llm, embedder))
    for arg in sys.argv[1:]:
        path = find_file(arg)
        csg = asyncio.run(lane.extract(
            "smoke-" + path.stem, "smoke-hash", path.name, path.read_bytes()))
        summarize(csg)


if __name__ == "__main__":
    main()
