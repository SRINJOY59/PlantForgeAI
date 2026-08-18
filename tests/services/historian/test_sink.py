"""The sink's parsing and its at-least-once contract.

No live database here: the DB is faked so the loop's discipline - parse
tolerantly, insert THEN ack, never ack an un-inserted batch - can be pinned
without provisioning Timescale.
"""

from datetime import datetime, timezone

import fakeredis
import pytest

from plantmind_core.timeseries import TelemetryRow
from historian.sink import GROUP, STREAM, TelemetrySink


def test_from_stream_parses_a_normal_sample():
    row = TelemetryRow.from_stream({
        "tag_id": "REACTOR.T", "timestamp": "2026-08-18T09:00:00Z",
        "value": "122.9", "unit": "degC", "status": "GOOD"})
    assert row.tag_id == "REACTOR.T"
    assert row.value == 122.9
    assert row.quality == "GOOD" and row.unit == "degC"
    assert row.ts == datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)


def test_from_stream_tolerates_bad_value_and_missing_fields():
    # a BAD sample keeps its row but nulls the value; a row with no tag is dropped
    bad = TelemetryRow.from_stream({"tag_id": "X", "value": "n/a", "status": "BAD"})
    assert bad.value is None and bad.quality == "BAD"
    assert TelemetryRow.from_stream({"value": "1.0"}) is None


class FakeDB:
    def __init__(self, fail_times=0):
        self.written = []
        self._fail_times = fail_times

    def ensure_schema(self):
        pass

    def insert_batch(self, rows):
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("db down")
        self.written.extend(rows)
        return len(rows)


def make_sink(db):
    r = fakeredis.FakeRedis(decode_responses=True)
    return TelemetrySink(db, r, batch=100, flush_ms=50), r


def publish(r, **fields):
    r.xadd(STREAM, fields)


def test_drain_inserts_then_acks():
    db = FakeDB()
    sink, r = make_sink(db)
    sink._ensure_group()
    publish(r, tag_id="REACTOR.T", timestamp="2026-08-18T09:00:00Z", value="122.9",
            unit="degC", status="GOOD")
    publish(r, tag_id="REACTOR.P", timestamp="2026-08-18T09:00:00Z", value="2705",
            unit="kPa", status="GOOD")

    assert sink._drain_once(">") == ">"

    assert [row.tag_id for row in db.written] == ["REACTOR.T", "REACTOR.P"]
    # both acked -> nothing pending for this consumer group
    pending = r.xpending(STREAM, GROUP)
    assert pending["pending"] == 0


def test_failed_insert_leaves_the_batch_unacked_for_redelivery():
    db = FakeDB(fail_times=1)          # first insert raises, batch must survive
    sink, r = make_sink(db)
    sink._ensure_group()
    publish(r, tag_id="REACTOR.T", timestamp="2026-08-18T09:00:00Z", value="122.9",
            unit="degC", status="GOOD")

    # live read delivers the entry, insert fails before ack -> it stays pending
    with pytest.raises(RuntimeError):
        sink._drain_once(">")
    assert r.xpending(STREAM, GROUP)["pending"] == 1

    # recovery read ("0") reclaims the pending entry; db is healthy now, so it
    # lands and acks - at least once, never lost
    assert sink._drain_once("0") == "0"
    assert len(db.written) == 1
    assert r.xpending(STREAM, GROUP)["pending"] == 0
