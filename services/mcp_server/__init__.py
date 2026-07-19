"""PlantMind's MCP server - the plant's knowledge as tools any MCP client
(Claude Desktop, Claude Code, ...) can call without opening the app.

Deliberately empty of imports: __main__ must install the logging guard BEFORE
anything imports plantmind_core (whose telemetry logs to stdout, which would
corrupt the MCP stdio framing). A re-export here would defeat that ordering.

The package is named mcp_server, not mcp, on purpose: services/ sits on
PYTHONPATH, and a package named mcp would shadow the MCP SDK itself.
"""
