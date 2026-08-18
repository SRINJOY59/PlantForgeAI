"""The Diagnostician - the deterministic extract-then-match pipeline.

A fake reader stands in for the historian, handing back a canned window, so the
orchestration is pinned without a database: a real episode yields a live
signature and a ranked match, an empty window yields None (never a false all-
clear), and a moved-but-unknown plant yields a signature with no matches.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from plantmind_core.schemas import FaultMode, FaultSignature, TagDeviation
from diagnostics.diagnose import Diagnostician, DiagnosisResult


@dataclass
class Row:
    ts: datetime
    tag_id: str
    value: float
    quality: str = "GOOD"
    unit: str = ""


T0 = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


class FakeReader:
    """Returns a fixed window regardless of the query - the pipeline under test
    is extract+match, not the historian's SQL."""
    def __init__(self, samples):
        self._samples = samples
        self.calls = []

    def around(self, tag_ids, moment, before_s, after_s):
        self.calls.append((tuple(tag_ids), moment, before_s, after_s))
        return list(self._samples)


def _episode(tag, baseline, spiked):
    """30s flat at `baseline`, then 30s flat at `spiked` - one clear step."""
    rows = [Row(T0 + timedelta(seconds=i), tag,
                baseline + (0.02 if i % 2 else -0.02)) for i in range(30)]
    rows += [Row(T0 + timedelta(seconds=30 + i), tag, spiked) for i in range(30)]
    return rows


ONSET = T0 + timedelta(seconds=30)

# a library with the fault our fake episode will reproduce
LIB = [
    FaultMode(
        id="faultmode:IDV-4", cause_id="IDV-4", cause_label="coolant step",
        unit_areas=["REACTOR"],
        signature=FaultSignature(
            deviations=[TagDeviation(tag_id="REACTOR.T", direction="high",
                                     magnitude=20.0, onset_offset_s=1.0,
                                     first_mover_rank=0)],
            window_s=60.0, source="sim", cause_id="IDV-4"),
    ),
]

TAGS = ["REACTOR.T", "REACTOR.P"]


def test_a_real_episode_yields_signature_and_top_match():
    reader = FakeReader(_episode("REACTOR.T", 100.0, 130.0))
    diag = Diagnostician(reader, LIB, TAGS)

    result = diag.diagnose_at(ONSET, before_s=30, after_s=30)

    assert isinstance(result, DiagnosisResult)
    assert result.signature.source == "plant"          # a live signature
    assert len(result.signature.deviations) == 1
    assert result.top is not None
    assert result.top.cause_id == "IDV-4"
    # the reader was asked for exactly the tags and window we configured
    assert reader.calls[0][0] == tuple(TAGS)
    assert reader.calls[0][2] == 30 and reader.calls[0][3] == 30


def test_empty_window_returns_none_not_all_clear():
    diag = Diagnostician(FakeReader([]), LIB, TAGS)
    assert diag.diagnose_at(ONSET) is None


def test_a_moved_plant_with_no_library_match_has_signature_but_no_matches():
    # plant clearly moved, but on a tag no fault mode knows about
    reader = FakeReader(_episode("STRIPPER.T", 60.0, 90.0))
    diag = Diagnostician(reader, LIB, ["STRIPPER.T"])

    result = diag.diagnose_at(ONSET, before_s=30, after_s=30)
    assert result is not None
    assert len(result.signature.deviations) == 1        # it saw the excursion
    assert result.matches == []                          # nothing in the library fits
    assert result.top is None


def test_reload_re_reads_the_library_from_the_store():
    class FakeStore:
        def __init__(self):
            self._modes = []
        def all(self):
            return list(self._modes)

    store = FakeStore()
    diag = Diagnostician(FakeReader([]), [], TAGS, store=store)
    assert diag.library_size == 0

    store._modes = LIB
    diag.reload()
    assert diag.library_size == 1
