"""Telemetry sink: tails the live plant:telemetry stream and lands every
sample in the historian.

A stream tailer in the shape of the watchers - a consumer group over
plant:telemetry, its own so it drains the full stream independently of the
alarm watchers - but where a watcher decides, this one only records. It is the
seam between the ephemeral transport (Redis, capped, live) and the durable
system of record (Timescale), and it is deliberately dumb: parse, batch, COPY,
ack. All the meaning is added downstream, off the recorded history.

    python -m historian.sink

Delivery is at-least-once. A batch is acked only after its COPY commits, so a
crash between commit and ack redelivers and re-inserts - a duplicate sample,
never a lost one, which for a historian is the safe direction to round.
"""

from __future__ import annotations

import time

import redis

from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger
from plantmind_core.timeseries import TelemetryRow, TimeseriesDB

log = get_logger("historian.sink")

STREAM = "plant:telemetry"
GROUP = "historian"
CONSUMER = "historian-sink-1"


class TelemetrySink:
    def __init__(self, db: TimeseriesDB, redis_client, batch: int, flush_ms: int):
        self._db = db
        self._r = redis_client
        self._batch = batch
        self._flush_ms = flush_ms

    @classmethod
    def from_settings(cls) -> "TelemetrySink | None":
        db = TimeseriesDB.from_settings()
        if db is None:
            return None
        s = get_settings()
        r = redis.Redis.from_url(s.redis_url, decode_responses=True)
        return cls(db, r, s.historian_batch_rows, s.historian_flush_ms)

    def _ensure_group(self):
        try:
            self._r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
        except redis.ResponseError:
            pass          # BUSYGROUP: the group already exists, which is fine

    def _ensure_schema(self):
        # the cloud DB may not be reachable the instant this boots; keep trying
        # rather than crash-loop the container through the orchestrator
        delay = 2
        while True:
            try:
                self._db.ensure_schema()
                return
            except Exception as e:
                log.warning("historian schema not ready, retrying",
                            error=str(e)[:160], retry_in_s=delay)
                time.sleep(delay)
                delay = min(delay * 2, 30)

    def run(self):
        self._ensure_group()
        self._ensure_schema()
        log.info("historian sink running", stream=STREAM, group=GROUP,
                 batch=self._batch, flush_ms=self._flush_ms)

        # Start in recovery: id "0" reads this consumer's pending (unacked)
        # entries, so a batch left behind by a crash is reclaimed before we
        # follow the live tail. _drain_once flips to ">" once the backlog clears.
        cursor = "0"
        while True:
            try:
                cursor = self._drain_once(cursor)
            except KeyboardInterrupt:
                log.info("historian sink shutting down")
                break
            except Exception as e:
                # transport or DB blip: the failed batch is still pending and
                # unacked, so drop back into recovery and retry it after a beat
                log.error("historian sink loop error", error=str(e)[:200])
                time.sleep(2)
                cursor = "0"

    def _drain_once(self, cursor: str) -> str:
        """Read one batch from `cursor`, land it, ack it; return the next cursor.

        cursor is "0" while reclaiming pending entries and ">" while following
        the live tail. A ">" read that fails leaves its batch pending, so the
        caller resets to "0" to reclaim it - that redelivery is the whole reason
        the sink reads a group rather than the raw stream.
        """
        resp = self._r.xreadgroup(
            GROUP, CONSUMER, {STREAM: cursor},
            count=self._batch, block=self._flush_ms)
        entries = resp[0][1] if resp else []
        if not entries:
            # nothing pending (recovery drained) or a live-tail timeout: follow live
            return ">"

        rows: list[TelemetryRow] = []
        ids: list[str] = []
        for entry_id, fields in entries:
            ids.append(entry_id)
            row = TelemetryRow.from_stream(fields)
            if row is not None:
                rows.append(row)

        # Land THEN ack. insert_batch raises on failure, before the ack, so the
        # batch stays pending and the run loop reclaims it via cursor "0".
        written = self._db.insert_batch(rows)
        self._r.xack(STREAM, GROUP, *ids)
        log.debug("historian batch landed", read=len(ids), written=written)

        # keep scanning pending while recovering; stay on the live tail otherwise
        return "0" if cursor != ">" else ">"


def main():
    sink = TelemetrySink.from_settings()
    if sink is None:
        # No DSN: the historian is switched off for this deployment. Idle
        # instead of exiting, so the service sits benign in the stack rather
        # than restart-looping and lighting up the dashboard red.
        log.warning("TIMESCALE_DSN not set - historian disabled, sink idling")
        while True:
            time.sleep(3600)
    sink.run()


if __name__ == "__main__":
    main()
