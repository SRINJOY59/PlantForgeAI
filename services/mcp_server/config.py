"""MCP-server-only settings, read from the environment the MCP client passes
when it launches us (Claude Desktop's "env" block / claude mcp add --env)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class McpConfig:
    gateway_url: str          # where /ask, /moc/assess and /metrics live
    token: str                # Supabase JWT if the gateway runs with auth on

    @classmethod
    def from_env(cls) -> "McpConfig":
        return cls(
            gateway_url=os.environ.get("PLANTMIND_GATEWAY_URL",
                                       "http://localhost:8000"),
            token=os.environ.get("PLANTMIND_TOKEN", ""))
