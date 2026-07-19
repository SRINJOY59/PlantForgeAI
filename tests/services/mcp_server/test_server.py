"""The MCP layer is thin on purpose, so what gets pinned is the contract:
every tool registered under its exact name (a rename breaks every connected
client silently), the response shapes a client's model reasons over, and tag
normalisation so chat-typed tags hit real graph nodes."""

import asyncio

from mcp_server.config import McpConfig
from mcp_server.server import PlantMindMCP
from mcp_server.toolsets import GraphLookupToolset, QaToolset
from conftest import FakeGateway, FakeGraph

EXPECTED_TOOLS = {
    "ask_plant", "assess_change", "plant_status",
    "get_failure_history", "get_connected_equipment",
    "get_governing_clauses", "get_documents_mentioning",
    "get_fix_procedures", "get_work_orders",
}


def build():
    return PlantMindMCP(config=McpConfig(gateway_url="http://fake", token=""),
                        gateway=FakeGateway(), graph=FakeGraph())


def test_every_tool_is_registered_under_its_contract_name():
    tools = asyncio.run(build().app.list_tools())
    assert {t.name for t in tools} == EXPECTED_TOOLS


def test_every_tool_carries_a_description_for_the_clients_model():
    # the docstring IS the schema the model chooses tools by; an empty one
    # makes the tool invisible in practice
    tools = asyncio.run(build().app.list_tools())
    assert all(t.description and len(t.description) > 20 for t in tools)


def test_ask_plant_shapes_citations_to_names_the_model_can_cite():
    out = QaToolset(FakeGateway()).ask_plant("how many failures?")
    assert out["answer"].startswith("Four seal failures")
    # filename preferred, doc_id as the fallback - never a missing key
    assert out["citations"][0]["document"] == "work_orders.csv"
    assert out["citations"][1]["document"] == "noname99"
    assert out["corrections"][0]["author"] == "eng@plant"


def test_lookups_normalise_the_tag_before_touching_the_graph():
    graph = FakeGraph()
    toolset = GraphLookupToolset(graph)
    toolset.get_failure_history("  p-101a ")
    toolset.get_work_orders("k-301")
    assert graph.calls == [("failure_history", "P-101A"),
                           ("work_orders", "K-301")]


def test_qa_and_moc_go_through_the_gateway_not_around_it():
    # policy (rate limits, auth) lives on the gateway; the MCP path must use it
    gateway = FakeGateway()
    server = PlantMindMCP(config=McpConfig("http://fake", ""),
                          gateway=gateway, graph=FakeGraph())
    QaToolset(gateway).ask_plant("q")
    assert gateway.asked == ["q"]
    assert server.app is not None
