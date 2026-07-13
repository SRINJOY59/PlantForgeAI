import asyncio

from plantmind_core.schemas import EdgeType, NodeType
from extraction.pnid.extractor import (
    Component, ComponentList, Connection, ConnectionList, PnidExtractor,
)
from conftest import SAMPLES, FakeLLM

SVG = (SAMPLES / "pnid_unit100.svg").read_bytes()

COMPONENTS = ComponentList(components=[
    Component(tag="T-101", kind="equipment", description="feed tank"),
    Component(tag="P-101A", kind="equipment"),
    Component(tag="P-101B", kind="equipment"),
    Component(tag="E-204", kind="equipment"),
    Component(tag="V-203", kind="equipment"),
    Component(tag="K-301", kind="equipment"),
    Component(tag="PI-102", kind="instrument"),
    Component(tag="PSV-204", kind="valve"),
    Component(tag="feed line", kind="other"),          # no tag grammar -> dropped
])

CONNECTIONS = ConnectionList(connections=[
    Connection(from_tag="T-101", to_tag="P-101A"),
    Connection(from_tag="T-101", to_tag="P-101B"),
    Connection(from_tag="P-101A", to_tag="E-204"),
    Connection(from_tag="E-204", to_tag="V-203"),
    Connection(from_tag="V-203", to_tag="K-301"),
    Connection(from_tag="V-203", to_tag="PSV-204"),
    Connection(from_tag="V-203", to_tag="X-999"),      # unknown endpoint -> dropped
    Connection(from_tag="V-203", to_tag="V-203"),      # self-loop -> dropped
])


def extract():
    llm = FakeLLM(COMPONENTS, CONNECTIONS)
    extractor = PnidExtractor(llm)
    csg = asyncio.run(extractor.extract("doc-pnid", "hash-pnid",
                                        "pnid_unit100.svg", SVG))
    return csg, llm


def test_svg_goes_to_llm_as_xml_text_not_image():
    _, llm = extract()

    kinds = [c[0] for c in llm.calls]
    assert kinds == ["structured", "structured"]       # never the vision path
    assert "<svg" in llm.calls[0][1][0]["content"]


def test_components_validated_and_typed():
    csg, _ = extract()

    surfaces = {n.surface_form for n in csg.nodes}
    assert "feed line" not in surfaces                  # grammar filter
    assert {"T-101", "P-101A", "V-203", "PSV-204"} <= surfaces

    psv = next(n for n in csg.nodes if n.surface_form == "PSV-204")
    assert psv.type == NodeType.INSTRUMENT              # PSV prefix
    tank = next(n for n in csg.nodes if n.surface_form == "T-101")
    assert tank.type == NodeType.EQUIPMENT
    assert tank.props["description"] == "feed tank"


def test_connections_filtered_to_known_endpoints():
    csg, _ = extract()

    connected = [(e.src, e.dst) for e in csg.edges
                 if e.type == EdgeType.CONNECTED_TO]
    assert ("T-101", "P-101A") in connected
    assert ("V-203", "K-301") in connected
    assert len(connected) == 6                          # bogus + self-loop gone


def test_pass2_prompt_carries_pass1_tags():
    _, llm = extract()

    pass2_prompt = llm.calls[1][1][0]["content"]
    assert "P-101A" in pass2_prompt and "K-301" in pass2_prompt


def test_every_component_cites_the_drawing():
    csg, _ = extract()

    mentions = {e.src for e in csg.edges if e.type == EdgeType.MENTIONED_IN}
    tags_in_graph = {n.surface_form for n in csg.nodes
                     if n.type in (NodeType.EQUIPMENT, NodeType.INSTRUMENT)}
    assert mentions == tags_in_graph
