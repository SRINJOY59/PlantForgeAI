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

from plantmind_core.aio import run_sync
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
ALARM_CURSOR = "agents-tep-alerts-cursor"
# alarms investigated per tick. They run concurrently, so this is the width
# of one batch rather than a serial cost.
ALARM_BATCH = 5
COMPLIANCE_INTERVAL_S = 3600
STANDARDS_INTERVAL_S = 86400
# How long a swept alert stays claimed. The sweeps re-derive the same
# standing conditions every hour, so without a lapse each one is announced
# once ever and the page looks empty from the second sweep onward; with a
# day, an obligation that is still breached is re-raised once a day.
SWEPT_ALERT_TTL_S = 86400


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
        block_ms=500,
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
        self.tick_alarms()

        # 3. Periodic tasks
        if time.time() - self._last_compliance >= self._interval:
            self.run_compliance()
        if self._standards and (time.time() - self._last_standards >= self._standards_interval):
            self.run_standards_watch()

    def tick_alarms(self):
        """Investigate the process alarms that arrived since the last tick."""
        alert_cursor = self._bus.get_cursor(ALARM_CURSOR) or "0-0"
        try:
            entries = self._bus._r.xread({"alerts:critical": alert_cursor},
                                         count=ALARM_BATCH, block=100)
        except Exception as e:
            log.warning("RCA: failed to read alerts:critical stream", error=str(e))
            return
        if not entries:
            return

        pending, last_id = [], None
        for _stream, messages in entries:
            for entry_id, fields in messages:
                last_id = entry_id
                coro = self._route_alarm(entry_id, fields.get("payload"))
                if coro is not None:
                    pending.append((entry_id, coro))

        # The cursor advances over the whole batch, investigated or not: an
        # entry this runtime has no handler for is finished with, not deferred.
        # Advancing it before the investigations also means a crash mid-batch
        # cannot put the runtime in a loop re-investigating the same alarms.
        if last_id:
            self._bus.set_cursor(ALARM_CURSOR, last_id)

        if pending:
            run_sync(self._investigate_all(pending))

    def _route_alarm(self, entry_id: str, payload_str):
        """-> the coroutine that should investigate this entry, or None.

        Only the simulators' process alarms are investigated here. This runtime
        publishes onto the very stream it is reading - compliance findings,
        failure patterns, and the investigations it wrote moments ago - and all
        of those carry severity warning or critical too. Selecting on severity
        therefore fed the runtime its own output back as though it were a plant
        alarm: an overdue-inspection notice reached the TEP alarm handler with
        no tag to investigate, spent an LLM call on it, and published an
        investigation of nothing next to the alert it was meant to explain.
        Kind is the honest discriminator, and 'rule' is what separates the
        CSTR/column watchers' alarms from the TEP watcher's.
        """
        if not payload_str:
            return None
        try:
            payload = json.loads(payload_str)
        except (ValueError, TypeError) as e:
            log.warning("RCA: unparseable alert payload", entry_id=entry_id, error=str(e))
            return None

        if payload.get("type") == "investigation":
            return None                      # our own answer, not a question
        if payload.get("kind") != "process_limit":
            return None                      # compliance / failure / standards
        if payload.get("rule"):
            return self._process_limit_handler.handle_process_limit(entry_id, payload)
        if payload.get("tag_id"):
            return self._tep_alarm_handler.handle_tep_alarm(entry_id, payload)
        return None

    async def _investigate_all(self, pending: list):
        """Investigate one batch of alarms concurrently.

        Serially a batch cost the sum of its investigations, and each one is a
        multi-step tool-calling conversation with a reasoning model - so a
        batch could hold the tick for minutes while the alarms it was meant to
        explain sat unanswered on the operator's screen and new ones queued
        behind them. Concurrency here is still bounded: the LLM client holds
        one process-wide semaphore, so this changes how long the runtime waits,
        not how hard it hits the provider.
        """
        results = await asyncio.gather(*(coro for _, coro in pending),
                                       return_exceptions=True)
        for (entry_id, _), result in zip(pending, results):
            if isinstance(result, BaseException):
                log.warning("RCA: investigation failed", entry_id=entry_id,
                            error_type=type(result).__name__,
                            error=str(result)[:200])

    def run_compliance(self):
        self._last_compliance = time.time()
        alerts = self._compliance.scan(date.today().isoformat(), self._bus.graph_version())
        self._emit(alerts)

    def run_standards_watch(self):
        self._last_standards = time.time()
        try:
            alerts = run_sync(self._standards.scan(self._bus.graph_version()))
        except Exception as e:
            log.warning("standards watch failed", error=str(e)[:160])
            return
        self._emit(alerts)

    def _emit(self, alerts: list):
        for alert in alerts:
            self._reader.name_citations(alert.citations)
            if self._bus.claim_alert(alert.fingerprint, ttl_seconds=SWEPT_ALERT_TTL_S):
                self._bus.publish_alert(alert.model_dump_json())
                log.info("alert raised", kind=alert.kind, severity=alert.severity, title=alert.title)


def main():
    AgentsRuntime.from_settings().run()


if __name__ == "__main__":
    main()
