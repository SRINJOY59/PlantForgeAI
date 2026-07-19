"""Entry point:  PYTHONPATH=services python -m mcp_server  (cwd: plantmind).

Order is the whole point of this file: the logging guard must land before any
plantmind_core import, or telemetry's stdout handlers corrupt the MCP stdio
framing and the client silently drops us.
"""

import sys
from pathlib import Path

# make the package runnable even if PYTHONPATH is incomplete
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_server.logging_guard import reroute_to_stderr

reroute_to_stderr()

from mcp_server.server import PlantMindMCP        # noqa: E402  (guard first)

PlantMindMCP().run()
