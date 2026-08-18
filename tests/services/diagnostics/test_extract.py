"""The signature extractor - the statistical core of the memory layer.

Synthetic windows only: a fault is a tag that leaves its baseline band and
stays out, and these build exactly that so the three things a signature must
get right - which tags, which way, in what order - can be pinned without a
simulator or a database.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from plantmind_core.schemas import FaultSignature
from diagnostics.signature import extract_signature


@dataclass
class Row:
    ts: datetime
    tag_id: str
    value: float


T0 = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


def series(tag, start_offset, n, fn):
    """n one-second samples of `tag`, value = fn(i)."""
    return [Row(T0 + timedelta(seconds=start_offset + i), tag, fn(i)) for i in range(n)]


def test_a_steady_tag_produces_no_deviation():
    # 60s of a tag sitting at 100 with tiny noise, onset halfway - nothing moved
    rows = series("STEADY", 0, 60, lambda i: 100.0 + (0.01 if i % 2 else -0.01))
    sig = extract_signature(rows, onset_ts=T0 + timedelta(seconds=30))
    assert isinstance(sig, FaultSignature)
    assert sig.deviations == []


def test_a_step_change_is_captured_with_direction_and_magnitude():
    # flat at 100 for 30s, then steps to 130 - a clear high deviation
    rows = series("REACTOR.T", 0, 30, lambda i: 100.0 + (0.05 if i % 2 else -0.05))
    rows += series("REACTOR.T", 30, 30, lambda i: 130.0)
    sig = extract_signature(rows, onset_ts=T0 + timedelta(seconds=30),
                            cause_id="IDV-4", cause_label="coolant step")

    assert sig.cause_id == "IDV-4"
    assert len(sig.deviations) == 1
    d = sig.deviations[0]
    assert d.tag_id == "REACTOR.T" and d.direction == "high"
    assert d.magnitude > 10          # 30-unit step over ~0.05 std is large
    assert d.first_mover_rank == 0


def test_a_downward_deviation_reads_as_low():
    rows = series("SEP.LiqFlow", 0, 30, lambda i: 60.0 + (0.05 if i % 2 else -0.05))
    rows += series("SEP.LiqFlow", 30, 30, lambda i: 5.0)
    sig = extract_signature(rows, onset_ts=T0 + timedelta(seconds=30))
    assert sig.deviations[0].direction == "low"


def test_first_mover_ordering_captures_the_cascade():
    # A moves at onset, B follows 10s later, C never moves. Order is the point.
    rows = []
    rows += series("A", 0, 30, lambda i: 10.0 + (0.02 if i % 2 else -0.02))
    rows += series("A", 30, 30, lambda i: 40.0)                 # jumps at onset
    rows += series("B", 0, 40, lambda i: 20.0 + (0.02 if i % 2 else -0.02))
    rows += series("B", 40, 20, lambda i: 50.0)                 # jumps at onset+10
    rows += series("C", 0, 60, lambda i: 5.0 + (0.02 if i % 2 else -0.02))

    sig = extract_signature(rows, onset_ts=T0 + timedelta(seconds=30))
    ranked = {d.tag_id: d.first_mover_rank for d in sig.deviations}
    assert "C" not in ranked                    # steady tag excluded
    assert ranked["A"] == 0 and ranked["B"] == 1
    assert sig.deviations[0].onset_offset_s < sig.deviations[1].onset_offset_s


def test_a_single_spike_is_not_a_deviation():
    # one sample pokes out then returns - below the sustained-breach floor
    rows = series("NOISY", 0, 30, lambda i: 100.0 + (0.05 if i % 2 else -0.05))
    post = series("NOISY", 30, 30, lambda i: 100.0 + (0.05 if i % 2 else -0.05))
    post[5].value = 200.0                       # lone spike
    sig = extract_signature(rows + post, onset_ts=T0 + timedelta(seconds=30))
    assert sig.deviations == []


def test_a_tag_with_no_baseline_is_skipped():
    # samples only after onset -> nothing to score against, no false positive
    rows = series("LATE", 30, 30, lambda i: 999.0)
    sig = extract_signature(rows, onset_ts=T0 + timedelta(seconds=30))
    assert sig.deviations == []
