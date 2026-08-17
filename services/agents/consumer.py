"""The agents runtime: a long-lived process that tails the graph delta
stream and reacts. Event-driven (a delta fires the failure watcher) plus
periodic (compliance is swept on an interval). Alerts are deduped by
fingerprint and published to the alert stream for the UI to tail.

    python -m agents.consumer
"""

import asyncio
import json
import time
from datetime import date

from plantmind_core.bus import RedisBus
from plantmind_core.telemetry import get_logger

from agents.handlers import DeltaHandler, ProcessLimitHandler, TepAlarmHandler
from agents.reader import AgentReader
from agents.usecases import (
    ComplianceScanner,
    InvestigatorAgent,
    StandardsWatcher,
    WebRevisionSource,
    WorkOrderDrafter,
)

log = get_logger("agents.consumer")

CURSOR = "agents-deltas"
COMPLIANCE_INTERVAL_S = 3600
STANDARDS_INTERVAL_S = 86400


class AgentsRuntime:
    def __init__(
        self,
        bus,
        reader,
        investigator=None,
        cache=None,
        embedder=None,
        compliance_interval=COMPLIANCE_INTERVAL_S,
        standards=None,
        standards_interval=STANDARDS_INTERVAL_S,
        block_ms=15000,
        drafter=None,
    ):
        self._bus = bus
        self._reader = reader
        self._investigator = investigator or InvestigatorAgent(reader)
        self._drafter = drafter or WorkOrderDrafter()
        self._compliance = ComplianceScanner(reader)
        self._standards = standards
        self._cache = cache
        self._embedder = embedder
        self._interval = compliance_interval
        self._standards_interval = standards_interval
        self._block_ms = block_ms
        self._last_compliance = 0.0
        self._last_standards = 0.0

        # Specialized event handlers
        self._delta_handler = DeltaHandler(
            bus=self._bus,
            reader=self._reader,
            investigator=self._investigator,
            drafter=self._drafter,
            cache=self._cache,
            embedder=self._embedder,
        )
        self._tep_alarm_handler = TepAlarmHandler(
            bus=self._bus,
            reader=self._reader,
            investigator=self._investigator,
        )
        self._process_limit_handler = ProcessLimitHandler(
            bus=self._bus,
            reader=self._reader,
            investigator=self._investigator,
        )

    @classmethod
    def from_settings(cls) -> "AgentsRuntime":
        from plantmind_core.cache import AnswerCache
        from plantmind_core.config import get_settings
        from plantmind_core.llm import get_embedder, get_llm

        bus = RedisBus.from_settings()
        reader = AgentReader.from_settings()
        standards = (
            StandardsWatcher(reader, bus, WebRevisionSource(get_llm()))
            if get_settings().standards_watch_enabled
            else None
        )
        return cls(
            bus,
            reader,
            cache=AnswerCache.from_settings(),
            embedder=get_embedder(),
            standards=standards,
        )

    def run(self):
        log.info("agents runtime started")
        self.run_compliance()
        while True:
            self.tick()

    def tick(self):
        # 1. Delta-driven failure patterns
        cursor = self._bus.get_cursor(CURSOR)
        for entry_id, payload in self._bus.read_deltas(cursor, self._block_ms):
            self._delta_handler.handle_delta(payload)
            self._bus.set_cursor(CURSOR, entry_id)

        # 2. Live telemetry alarms (RCA) from alerts:critical stream
        alert_cursor = self._bus.get_cursor("agents-tep-alerts-cursor") or "0-0"
        try:
            entries = self._bus._r.xread({"alerts:critical": alert_cursor}, count=5, block=100)
            if entries:
                for _stream, messages in entries:
                    for entry_id, fields in messages:
                        payload_str = fields.get("payload")
                        if payload_str:
                            try:
                                payload = json.loads(payload_str)
                                if (
                                    payload.get("severity") in ("critical", "warning")
                                    and payload.get("type") != "investigation"
                                ):
                                    asyncio.run(
                                        self._tep_alarm_handler.handle_tep_alarm(entry_id, payload)
                                    )
                                elif (
                                    payload.get("kind") == "process_limit"
                                    and payload.get("type") != "investigation"
                                ):
                                    asyncio.run(
                                        self._process_limit_handler.handle_process_limit(
                                            entry_id, payload
                                        )
                                    )
                            except Exception as alert_err:
                                log.warning("RCA: failed to process alert", error=str(alert_err))
                        self._bus.set_cursor("agents-tep-alerts-cursor", entry_id)
        except Exception as e:
            log.warning("RCA: failed to read alerts:critical stream", error=str(e))

        # 3. Periodic tasks
        if time.time() - self._last_compliance >= self._interval:
            self.run_compliance()
        if self._standards and (time.time() - self._last_standards >= self._standards_interval):
            self.run_standards_watch()

    def run_compliance(self):
        self._last_compliance = time.time()
        alerts = self._compliance.scan(date.today().isoformat(), self._bus.graph_version())
        self._emit(alerts)

    def run_standards_watch(self):
        self._last_standards = time.time()
        try:
            alerts = asyncio.run(self._standards.scan(self._bus.graph_version()))
        except Exception as e:
            log.warning("standards watch failed", error=str(e)[:160])
            return
        self._emit(alerts)

    def _emit(self, alerts: list):
        for alert in alerts:
            self._reader.name_citations(alert.citations)
            if self._bus.claim_alert(alert.fingerprint):
                self._bus.publish_alert(alert.model_dump_json())
                log.info("alert raised", kind=alert.kind, severity=alert.severity, title=alert.title)


def main():
    AgentsRuntime.from_settings().run()


if __name__ == "__main__":
    main()
