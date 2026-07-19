"""Pipeline health, so a client can tell 'no data yet' from 'broken'."""


class StatusToolset:
    def __init__(self, gateway):
        self._gateway = gateway

    def register(self, mcp) -> None:
        mcp.add_tool(self.plant_status)

    def plant_status(self) -> dict:
        """Pipeline health: current graph version and ingestion queue depths.
        Zero depths everywhere means the pipeline is idle (all documents
        processed)."""
        return self._gateway.metrics()
