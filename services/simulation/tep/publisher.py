"""Tennessee Eastman Process — Telemetry Publisher.

Publishes all TEP PV/MV tags to the plant:telemetry Redis stream.
Extends BaseTelemetryPublisher for pipeline batching and status handling.
"""
from __future__ import annotations
import redis
from simulation.base.publisher import BaseTelemetryPublisher
from simulation.tep.topology import TAG_UNITS


class TepTelemetryPublisher(BaseTelemetryPublisher):
    """Publishes all TEP PV and MV tags on every simulation tick."""

    def __init__(self, r: redis.Redis | None = None):
        super().__init__(r)

    def publish(self, state: dict) -> None:
        """Publish a full state_dict from TepProcessModel to plant:telemetry.

        Args:
            state: dict mapping tag_id → float value (from TepProcessModel.state_dict())
        """
        tags: dict[str, tuple[float, str]] = {}
        for tag_id, value in state.items():
            phy_unit = TAG_UNITS.get(tag_id, "")
            tags[tag_id] = (value, phy_unit)
        self.publish_tags(tags)
