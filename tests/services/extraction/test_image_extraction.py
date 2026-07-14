import asyncio

from plantmind_core.schemas import EdgeType, NodeType
from extraction.imaging.extractor import (
    ChartReading, DataPoint, ImageLane, ImageVerdict, Nameplate, Series,
)
from extraction.pnid.extractor import (
    Component, ComponentList, Connection, ConnectionList, PnidExtractor,
)
from extraction.text.extractor import TextExtractor
from extraction.text.relations import BatchFindings
from conftest import FakeEmbedder, FakeLLM

PNG = b"\x89PNG fake image bytes"


def lane(llm):
    embedder = FakeEmbedder()
    return ImageLane(llm, embedder, PnidExtractor(llm),
                     TextExtractor(llm, embedder))


def extract(llm):
    return asyncio.run(lane(llm).extract("doc-img", "hash-img",
                                         "photo.png", PNG))


def test_chart_becomes_searchable_data_chunk():
    llm = FakeLLM(
        ImageVerdict(kind="chart"),
        ChartReading(chart_type="line",
                     title="K-301 discharge temperature trend",
                     x_axis="date", y_axis="deg C",
                     series=[Series(name="discharge temp", points=[
                         DataPoint(x="2026-02-20", y="128"),
                         DataPoint(x="2026-03-02", y="141")])],
                     summary="K-301 discharge temperature rose steadily over "
                             "ten days before the trip."))

    csg = extract(llm)

    chart = next(n for n in csg.nodes if n.type == NodeType.CHUNK)
    assert chart.props["kind"] == "chart"
    assert chart.props["chart_type"] == "line"
    assert chart.props["series"][0]["points"][1]["y"] == "141"
    assert chart.props["embedding"] == [0.1, 0.2, 0.3]

    assert any(e.type == EdgeType.MENTIONED_IN and e.src == "K-301"
               for e in csg.edges)                    # tag pulled from summary
    assert any(e.type == EdgeType.PART_OF and e.dst == "doc-img"
               for e in csg.edges)


def test_nameplate_becomes_equipment_properties():
    llm = FakeLLM(
        ImageVerdict(kind="nameplate"),
        Nameplate(equipment_tag="P-101A", manufacturer="KSB",
                  model="MM-4402", serial_number="SN-88231",
                  ratings=["7.5 kW", "2900 rpm"]))

    csg = extract(llm)

    pump = next(n for n in csg.nodes if n.type == NodeType.EQUIPMENT)
    assert pump.surface_form == "P-101A"
    assert pump.props["serial_number"] == "SN-88231"
    assert "7.5 kW" in pump.props["ratings"]


def test_unreadable_nameplate_yields_document_only():
    llm = FakeLLM(ImageVerdict(kind="nameplate"),
                  Nameplate(equipment_tag="illegible"))

    csg = extract(llm)

    assert {n.type for n in csg.nodes} == {NodeType.DOCUMENT}


def test_drawing_verdict_delegates_to_pnid_extractor():
    llm = FakeLLM(
        ImageVerdict(kind="drawing"),
        ComponentList(components=[Component(tag="T-101"),
                                  Component(tag="P-101A")]),
        ConnectionList(connections=[Connection(from_tag="T-101",
                                               to_tag="P-101A")]))

    csg = extract(llm)

    assert any(e.type == EdgeType.CONNECTED_TO and e.src == "T-101"
               and e.dst == "P-101A" for e in csg.edges)


def test_document_verdict_transcribes_then_runs_text_pipeline():
    llm = FakeLLM(
        ImageVerdict(kind="document"),
        "# Field note\n\nObserved oil mist near K-301 bearing housing.",
        *[BatchFindings()] * 3)

    csg = extract(llm)

    assert any(n.type == NodeType.CHUNK and "oil mist" in n.props["text"]
               for n in csg.nodes)
    assert "K-301" in {n.surface_form for n in csg.nodes}
    assert llm.calls[1][0] == "vision_text"           # the OCR call happened
