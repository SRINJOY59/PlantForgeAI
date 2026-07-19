"""The composition root: config -> backends -> toolsets -> one FastMCP app.

Backends are injectable so tests build the whole server against fakes and
exercise the real registration and tool logic with no gateway, no Neo4j, and
no protocol in the way.
"""

from mcp.server.fastmcp import FastMCP

from mcp_server.backends import GatewayBackend, GraphBackend
from mcp_server.config import McpConfig
from mcp_server.toolsets import (ChangeToolset, GraphLookupToolset, QaToolset,
                                 StatusToolset)

INSTRUCTIONS = (
    "Knowledge graph of a process plant: equipment, failure history, work "
    "orders, procedures, governing standards, and engineer corrections. Use "
    "ask_plant for open questions (it retrieves, cites and answers); use the "
    "get_* tools for precise structured lookups; use assess_change before "
    "recommending any modification to equipment. Facts carry citations to "
    "plant documents - repeat them, do not invent plant data this server did "
    "not return.")


class PlantMindMCP:
    def __init__(self, config: McpConfig | None = None,
                 gateway=None, graph=None):
        config = config or McpConfig.from_env()
        gateway = gateway or GatewayBackend(config)
        graph = graph or GraphBackend()

        self._mcp = FastMCP("plantmind", instructions=INSTRUCTIONS)
        for toolset in (QaToolset(gateway), ChangeToolset(gateway),
                        GraphLookupToolset(graph), StatusToolset(gateway)):
            toolset.register(self._mcp)

    @property
    def app(self) -> FastMCP:
        return self._mcp

    def run(self) -> None:
        # stdio transport: the MCP client launches this process and owns it
        self._mcp.run()
