"""The diagnostics runtime: watch the alarm stream, diagnose live episodes.

A long-lived process, the standalone signal path. When the plant breaches a limit
the TEP watcher fires a process_limit alarm; this reads that stream, waits for the
cascade to develop and land in the historian, distils the episode into a live
signature, matches it against the learned library, and publishes a Diagnosis on
its own stream for the Diagnose view. No LLM here - it emits ranked candidates and
the evidence behind them, never a verdict.

Two things make it behave. First, it *defers*: a diagnosis fired the instant an
alarm arrives would read an empty post-onset window, because the reaction it needs
to score has not happened yet - so an armed episode waits `after_s` of wall time
for the plant to react and the historian to catch up before it reads. Second, it
*coalesces*: one fault trips many tags, each its own alarm, but they are one
episode with one cause. A single armed slot plus a cooldown turns that burst into
one diagnosis anchored at the first alarm - and the extractor, which looks across
every tag in the window, captures the rest of the cascade anyway.

    python -m diagnostics.service
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from plantmind_core import keys
from plantmind_core.bus import RedisBus
from plantmind_core.schemas import Diagnosis
from plantmind_core.telemetry import get_logger

from diagnostics.detector import DetectorStore, OnlinePCADetector, AnomalyEvent
from diagnostics.diagnose import Diagnostician

log = get_logger("diagnostics.service")

CURSOR = "diagnostics-alarms"
TELEMETRY_CURSOR = "diagnostics-telemetry"
ALARM_BATCH = 50

# lead-in and reaction windows for the diagnosis read (seconds)
BEFORE_S = 600
AFTER_S = 120
# wait past the sink's flush timer so the tail of the reaction has landed
FLUSH_MARGIN_S = 6

# after emitting, hold off re-arming for this long: the tags a fault trips do not
# all clear at once, and an episode should be diagnosed once, not once per tag.
COOLDOWN_S = 300

# re-read the library (and re-discover tags) on this cadence, so a campaign run
# while the service is up is picked up without a restart
LIBRARY_REFRESH_S = 600

# short block so the loop stays responsive to the flush timer while still parking
# instead of busy-spinning when the plant is quiet
POLL_BLOCK_MS = 1000

_LEVEL_SEVERITY = {
    "HH": "critical",
    "LL": "critical",
    "H": "warning",
    "L": "warning",
    "ML_ANOMALY": "warning",
}


@dataclass
class _Episode:
    """One armed, not-yet-diagnosed episode."""
    onset: datetime
    ready_at: float          # wall-clock epoch when the reaction window has filled
    tag: str
    level: str


class DiagnosticsRuntime:
    def __init__(self, bus, diagnostician: Diagnostician, *,
                 detector: OnlinePCADetector | None = None,
                 before_s: int = BEFORE_S, after_s: int = AFTER_S,
                 cooldown_s: int = COOLDOWN_S,
                 library_refresh_s: int = LIBRARY_REFRESH_S,
                 block_ms: int = POLL_BLOCK_MS, clock=time.time):
        self._bus = bus
        self._diag = diagnostician
        self._detector = detector
        self._before_s = before_s
        self._after_s = after_s
        self._cooldown_s = cooldown_s
        self._refresh_s = library_refresh_s
        self._block_ms = block_ms
        self._now = clock

        self._pending: _Episode | None = None
        self._cooldown_until = 0.0
        self._last_refresh = clock()
        self._telemetry_cursor = "$"

    @classmethod
    def from_settings(cls) -> "DiagnosticsRuntime | None":
        diag = Diagnostician.from_settings()
        if diag is None:
            log.warning("historian unconfigured; diagnostics runtime disabled")
            return None

        # Load calibrated PCA anomaly detector model if present
        store = DetectorStore()
        model = store.load()
        detector = OnlinePCADetector(model) if model is not None else None
        if detector is not None:
            log.info("ml pca anomaly detector active", tags=len(model.tags), k=model.k_components)
        else:
            log.info("no saved pca detector model found; running in envelope-only mode")

        return cls(RedisBus.from_settings(), diag, detector=detector)

    def run(self):
        if self._diag.library_size == 0:
            log.warning("fault library is empty; diagnoses will carry no matches "
                        "until a campaign has populated it "
                        "(python -m tools.build_fault_library)")
        self._seed_cursor()
        log.info("diagnostics runtime started", library=self._diag.library_size)
        while True:
            try:
                self.tick()
            except Exception:
                log.exception("diagnostics tick failed")
                time.sleep(1)

    def tick(self):
        self._ingest_alarms()
        self._ingest_telemetry_ml()
        self._flush_ready()
        self._maybe_refresh()

    def _ingest_telemetry_ml(self):
        """Feed live plant:telemetry stream samples to the ML PCA detector."""
        if self._detector is None:
            return

        try:
            entries = self._bus._r.xread({"plant:telemetry": self._telemetry_cursor}, count=100)
        except Exception:
            return

        if not entries:
            return

        # entries is [('plant:telemetry', [(entry_id, {tag_id, value, timestamp, ...}), ...])]
        for _, batch in entries:
            # Group samples by timestamp into multivariate dicts
            slices: dict[float, dict[str, float]] = {}
            for entry_id, fields in batch:
                self._telemetry_cursor = entry_id
                tag_id = fields.get("tag_id")
                if not tag_id:
                    continue
                try:
                    val = float(fields.get("value"))
                    raw_ts = fields.get("timestamp")
                    ts = float(raw_ts) if raw_ts else time.time()
                except (ValueError, TypeError):
                    continue

                ts_sec = round(ts)
                if ts_sec not in slices:
                    slices[ts_sec] = {}
                slices[ts_sec][tag_id] = val

            for ts_sec, sample_dict in sorted(slices.items()):
                event = self._detector.process_sample(sample_dict, ts=ts_sec)
                if event is not None:
                    self._maybe_arm_ml(event)

    def _maybe_arm_ml(self, event: AnomalyEvent):
        now = self._now()
        if self._pending is not None or now < self._cooldown_until:
            return

        onset_epoch = event.onset.timestamp()
        self._pending = _Episode(
            onset=event.onset,
            ready_at=onset_epoch + self._after_s + FLUSH_MARGIN_S,
            tag=event.trigger_tag,
            level="ML_ANOMALY",
        )
        log.warning("ml incipient anomaly armed episode", tag=self._pending.tag,
                    level=self._pending.level,
                    t2_ratio=event.t2_ratio, spe_ratio=event.spe_ratio,
                    diagnose_in_s=round(self._pending.ready_at - now))

    def _seed_cursor(self):
        """On a first-ever start (no stored cursor), begin at the alarm stream's
        tail rather than its head - a live diagnosis signal cares about what the
        plant does next, not about re-diagnosing every alarm since the volume was
        created. A restart with a stored cursor resumes where it left off."""
        if self._bus.get_cursor(CURSOR) != "0":
            return
        tail = self._bus.last_alert_id()
        if tail:
            self._bus.set_cursor(CURSOR, tail)
            log.info("no cursor; starting at alarm-stream tail", at=tail)

    # --- reading the alarm stream ------------------------------------------
    def _ingest_alarms(self):
        cursor = self._bus.get_cursor(CURSOR) or "0-0"
        entries = self._bus.read_alerts(cursor, self._block_ms)
        if not entries:
            return

        last_id = None
        for entry_id, payload_str in entries:
            last_id = entry_id
            payload = self._parse(payload_str)
            if payload is None or not self._is_live_alarm(payload):
                continue
            self._maybe_arm(payload)

        # advance over the whole batch: an alarm we didn't arm on (a duplicate
        # within an episode, or one that arrived during cooldown) is handled,
        # not deferred - and advancing before the diagnosis means a crash can't
        # loop us over the same alarms.
        if last_id:
            self._bus.set_cursor(CURSOR, last_id)

    @staticmethod
    def _parse(payload_str):
        try:
            return json.loads(payload_str) if payload_str else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _is_live_alarm(payload: dict) -> bool:
        """A real plant breach - not our own output, not a compliance/failure
        alert. The same honest discriminator the agents runtime routes on."""
        if payload.get("type") == "investigation":
            return False
        return payload.get("kind") == "process_limit" and bool(payload.get("tag_id"))

    def _maybe_arm(self, payload: dict):
        now = self._now()
        if self._pending is not None or now < self._cooldown_until:
            return                          # already following an episode / cooling down

        onset_epoch = self._onset_epoch(payload, now)
        self._pending = _Episode(
            onset=datetime.fromtimestamp(onset_epoch, tz=timezone.utc),
            ready_at=onset_epoch + self._after_s + FLUSH_MARGIN_S,
            tag=payload.get("tag_id", ""),
            level=payload.get("level", ""),
        )
        log.info("episode armed", tag=self._pending.tag, level=self._pending.level,
                 diagnose_in_s=round(self._pending.ready_at - now))

    @staticmethod
    def _onset_epoch(payload: dict, now: float) -> float:
        """The alarm's own timestamp is the onset; fall back to now if it is
        missing or unparseable rather than skip the episode."""
        ts = payload.get("timestamp")
        try:
            return float(ts)
        except (TypeError, ValueError):
            return now

    # --- diagnosing a ready episode ----------------------------------------
    def _flush_ready(self):
        if self._pending is None or self._now() < self._pending.ready_at:
            return
        episode = self._pending
        self._pending = None
        self._cooldown_until = self._now() + self._cooldown_s
        self._diagnose(episode)

    def _diagnose(self, episode: _Episode):
        severity = _LEVEL_SEVERITY.get(episode.level, "warning")
        result = self._diag.diagnose_at(
            episode.onset, before_s=self._before_s, after_s=self._after_s,
            severity=severity)
        if result is None:
            log.info("nothing recorded around onset; no diagnosis emitted",
                     tag=episode.tag)
            return

        diagnosis = Diagnosis(
            id=f"diag:{int(episode.onset.timestamp())}:{episode.tag}",
            onset=episode.onset.isoformat(),
            trigger_tag=episode.tag,
            trigger_level=episode.level,
            signature=result.signature,
            matches=result.matches,
            graph_version=self._bus.graph_version(),
        )
        self._bus.publish_diagnosis(diagnosis.model_dump_json())
        log.info("diagnosis published", tag=episode.tag,
                 deviations=len(result.signature.deviations),
                 candidates=len(result.matches),
                 top=result.top.cause_id if result.top else None)

    # --- housekeeping ------------------------------------------------------
    def _maybe_refresh(self):
        if self._now() - self._last_refresh < self._refresh_s:
            return
        self._last_refresh = self._now()
        self._diag.reload()
        self._diag.refresh_tags()


def main():
    runtime = DiagnosticsRuntime.from_settings()
    if runtime is None:
        log.error("diagnostics runtime could not start (no historian). Set "
                  "TIMESCALE_DSN to enable it.")
        return
    runtime.run()


if __name__ == "__main__":
    main()
