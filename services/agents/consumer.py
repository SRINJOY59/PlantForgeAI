"""The agents runtime: a long-lived process that tails the graph delta
stream and reacts. Event-driven (a delta fires the failure watcher) plus
periodic (compliance is swept on an interval). Alerts are deduped by
fingerprint and published to the alert stream for the UI to tail.

    python -m agents.consumer
"""

import asyncio
import time
from datetime import date

from plantmind_core.bus import RedisBus
from plantmind_core.schemas import GraphDelta
from plantmind_core.telemetry import get_logger

from agents.investigator import InvestigatorAgent
from agents.reader import AgentReader
from agents.watchers import ComplianceScanner, FailureWatcher

log = get_logger("agents.consumer")

CURSOR = "agents-deltas"
COMPLIANCE_INTERVAL_S = 3600


class AgentsRuntime:
    def __init__(self, bus, reader, investigator=None,
                 compliance_interval=COMPLIANCE_INTERVAL_S):
        self._bus = bus
        self._failures = FailureWatcher(reader)
        self._investigator = investigator or InvestigatorAgent(reader)
        self._compliance = ComplianceScanner(reader)
        self._interval = compliance_interval
        self._last_compliance = 0.0

    @classmethod
    def from_settings(cls) -> "AgentsRuntime":
        return cls(RedisBus.from_settings(), AgentReader.from_settings())

    def run(self):
        log.info("agents runtime started")
        self.run_compliance()                      # sweep once on startup
        while True:
            self.tick()

    def tick(self):
        cursor = self._bus.get_cursor(CURSOR)
        for entry_id, payload in self._bus.read_deltas(cursor, block_ms=15000):
            self._on_delta(payload)
            self._bus.set_cursor(CURSOR, entry_id)
        if time.time() - self._last_compliance >= self._interval:
            self.run_compliance()

    def _on_delta(self, payload: str):
        delta = GraphDelta.model_validate_json(payload)
        if "HAS_FAILURE" not in delta.new_edge_types:
            return
        # deterministic detection, then agentic investigation per trigger
        for trigger in self._failures.detect(delta.touched_node_ids,
                                             delta.graph_version):
            if not self._bus.claim_alert(
                    f"failure:{trigger.tag}:{trigger.mode}:{trigger.count}"):
                continue
            alert = asyncio.run(self._investigator.investigate(trigger))
            self._bus.publish_alert(alert.model_dump_json())
            log.info("alert raised", kind=alert.kind, severity=alert.severity,
                     title=alert.title)

    def run_compliance(self):
        self._last_compliance = time.time()
        alerts = self._compliance.scan(date.today().isoformat(),
                                       self._bus.graph_version())
        self._emit(alerts)

    def _emit(self, alerts: list):
        for alert in alerts:
            if self._bus.claim_alert(alert.fingerprint):
                self._bus.publish_alert(alert.model_dump_json())
                log.info("alert raised", kind=alert.kind,
                         severity=alert.severity, title=alert.title)


def main():
    AgentsRuntime.from_settings().run()


if __name__ == "__main__":
    main()
