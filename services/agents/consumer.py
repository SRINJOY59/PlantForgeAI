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
from agents.watchers import Trigger, family_of
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
RCA_REQUEST_CURSOR = "agents-rca-requests-cursor"
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
        auto_rca=False,
    ):
        self._bus = bus
        self._reader = reader
        # whether a simulator's process-limit alarm auto-spends an LLM RCA.
        # Off by default; the diagnostics service answers alarms deterministically
        # and LLM RCA is requested per-episode instead. See _route_alarm.
        self._auto_rca = auto_rca
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
        settings = get_settings()
        standards = (
            StandardsWatcher(reader, bus, WebRevisionSource(get_llm()))
            if settings.standards_watch_enabled
            else None
        )
        return cls(
            bus,
            reader,
            cache=AnswerCache.from_settings(),
            embedder=get_embedder(),
            standards=standards,
            auto_rca=settings.auto_rca_enabled,
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

        # 3. On-demand LLM RCA an operator asked for on one diagnosis
        self.tick_rca_requests()

        # 4. Periodic tasks
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
        if not self._auto_rca:
            # a simulator alarm is answered by the diagnostics service now -
            # signature + library match, deterministic and free. An LLM RCA is
            # spent only when an operator asks for one on a specific episode.
            return None
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

    # --- on-demand RCA -----------------------------------------------------
    def tick_rca_requests(self):
        """Run the LLM RCA an operator explicitly asked for on one diagnosis.

        This is the deliberate, per-episode spend that replaces auto-investigating
        every alarm. The investigation is grounded in the diagnosis the plant
        already produced - the matched fault mode and the observed cascade - so
        the model confirms or refutes a stated prior rather than starting cold.
        """
        cursor = self._bus.get_cursor(RCA_REQUEST_CURSOR) or "0-0"
        try:
            entries = self._bus.read_rca_requests(cursor, block_ms=0)
        except Exception as e:
            log.warning("on-demand RCA: failed to read request stream", error=str(e))
            return
        if not entries:
            return

        pending, last_id = [], None
        for entry_id, payload_str in entries:
            last_id = entry_id
            try:
                req = json.loads(payload_str) if payload_str else {}
            except (ValueError, TypeError):
                continue
            diag_id = req.get("diagnosis_id")
            if not diag_id or not self._bus.claim_rca_request(diag_id):
                continue                      # no id, or already in flight / done
            diag_json = self._bus.get_indexed_diagnosis(diag_id)
            if not diag_json:
                log.warning("on-demand RCA: diagnosis not found", diagnosis_id=diag_id)
                self._bus.release_rca_request(diag_id)
                continue
            try:
                diag = json.loads(diag_json)
            except (ValueError, TypeError):
                self._bus.release_rca_request(diag_id)
                continue
            pending.append((diag_id, self._investigate_diagnosis(diag)))

        if last_id:
            self._bus.set_cursor(RCA_REQUEST_CURSOR, last_id)
        if pending:
            run_sync(self._run_rca_batch(pending))

    async def _run_rca_batch(self, pending: list):
        results = await asyncio.gather(*(coro for _, coro in pending),
                                       return_exceptions=True)
        for (diag_id, _), result in zip(pending, results):
            if isinstance(result, BaseException):
                # free the claim so the operator can ask again after a failure
                self._bus.release_rca_request(diag_id)
                log.warning("on-demand RCA failed", diagnosis_id=diag_id,
                            error_type=type(result).__name__,
                            error=str(result)[:200])

    async def _investigate_diagnosis(self, diag: dict):
        diag_id = diag.get("id", "")
        trigger_tag = diag.get("trigger_tag", "")
        unit_area = trigger_tag.split(".")[0] if "." in trigger_tag else trigger_tag
        level = diag.get("trigger_level") or "H"
        sig = diag.get("signature") or {}
        devs = sig.get("deviations") or []
        matches = diag.get("matches") or []
        top = matches[0] if matches else {}

        family = family_of(unit_area)
        siblings = self._reader.family_history(family, level, exclude_tag=unit_area)
        trigger = Trigger(
            tag=unit_area, mode=f"{level} anomaly: {trigger_tag}",
            count=1, family=family, siblings=siblings, graph_version=0,
        )
        alert_context = {
            "tag_id": trigger_tag,
            "unit_area": unit_area,
            "alarm_level": level,
            "message": f"Live diagnosis {diag_id}",
            "plant": "Tennessee Eastman Process (TEP)",
            "diagnosis": {
                "matched_fault": top.get("cause_id"),
                "matched_label": top.get("cause_label"),
                "confidence": top.get("confidence"),
                "cascade": [
                    {"tag": d.get("tag_id"), "direction": d.get("direction"),
                     "z": d.get("magnitude"), "rank": d.get("first_mover_rank")}
                    for d in devs
                ],
                "candidates": [
                    {"cause_id": m.get("cause_id"), "label": m.get("cause_label"),
                     "confidence": m.get("confidence")} for m in matches
                ],
            },
        }

        log.info("on-demand RCA starting", diagnosis_id=diag_id, tag=trigger_tag,
                 matched=top.get("cause_id"))
        alert_obj, _ = await self._investigator.investigate_reasoned(
            trigger, alert_context=alert_context)
        self._reader.name_citations(alert_obj.citations)

        investigation_payload = {
            "type": "investigation",
            "diagnosis_id": diag_id,
            "alert_ref": diag_id,
            "summary": alert_obj.body,
            "affected_equipment": [unit_area],
            "unit_area": unit_area,
            "tag_id": trigger_tag,
            "matched_fault": top.get("cause_id"),
            "verified": alert_obj.verified,
            "citations": [c.model_dump() for c in alert_obj.citations],
            "timestamp": time.time(),
        }
        self._bus.publish_alert(json.dumps(investigation_payload))
        log.info("on-demand RCA published", diagnosis_id=diag_id)

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
