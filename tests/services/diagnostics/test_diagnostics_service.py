"""The diagnostics runtime - the standalone signal loop.

The historian and matcher are faked; what is pinned here is the loop's own
behaviour, the part that is easy to get subtly wrong: it waits for the reaction
window before diagnosing (deferral), turns one fault's burst of alarms into one
diagnosis (coalescing), does not re-arm while an episode is still clearing
(cooldown), and ignores its own output and the compliance feed (filtering). A
hand-driven clock makes 'later' a function call instead of a sleep.
"""

import json
from datetime import datetime, timezone

import pytest

from plantmind_core.schemas import (
    Diagnosis, DiagnosisMatch, FaultSignature, TagDeviation,
)
from diagnostics.diagnose import DiagnosisResult
from diagnostics.service import DiagnosticsRuntime


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class FakeBus:
    def __init__(self):
        self._cursors = {}
        self._inbox = []            # entries the next read_alerts returns
        self.published = []         # diagnosis JSON strings published

    def queue(self, *payloads):
        base = len(self._inbox)
        for i, p in enumerate(payloads):
            self._inbox.append((f"{base + i}-0", json.dumps(p)))

    def read_alerts(self, after_id, block_ms):
        out, self._inbox = self._inbox, []
        return out

    def get_cursor(self, name):
        return self._cursors.get(name, "0")

    def set_cursor(self, name, entry_id):
        self._cursors[name] = entry_id

    def graph_version(self):
        return 7

    def last_alert_id(self):
        return self._inbox[-1][0] if self._inbox else None

    def publish_diagnosis(self, diagnosis_json):
        self.published.append(diagnosis_json)
        return f"pub-{len(self.published)}"


class FakeDiag:
    def __init__(self, result="default"):
        self._result = result
        self.calls = []
        self.reloaded = 0
        self.tags_refreshed = 0

    @property
    def library_size(self):
        return 3

    def diagnose_at(self, onset, *, before_s, after_s, severity):
        self.calls.append((onset, severity))
        if self._result == "default":
            return _result(onset)
        return self._result            # None, or a preset DiagnosisResult

    def reload(self):
        self.reloaded += 1

    def refresh_tags(self):
        self.tags_refreshed += 1


def _result(onset):
    sig = FaultSignature(
        deviations=[TagDeviation(tag_id="REACTOR.T", direction="high",
                                 magnitude=12.0, onset_offset_s=1.0,
                                 first_mover_rank=0)],
        window_s=180.0, source="plant")
    match = DiagnosisMatch(fault_mode_id="faultmode:IDV-4", cause_id="IDV-4",
                           cause_label="coolant step", confidence=0.9)
    return DiagnosisResult(onset=onset, signature=sig, matches=[match])


def alarm(tag="REACTOR.T", level="HH", ts=1000.0, kind="process_limit",
          type_=None):
    p = {"kind": kind, "tag_id": tag, "level": level, "timestamp": ts}
    if type_:
        p["type"] = type_
    return p


def make_runtime(bus, diag, clock):
    # small windows so the arithmetic in the test is obvious
    return DiagnosticsRuntime(bus, diag, before_s=60, after_s=30,
                              cooldown_s=100, library_refresh_s=1000,
                              block_ms=0, clock=clock)


# --- deferral ---------------------------------------------------------------
def test_diagnosis_is_deferred_until_the_reaction_window_fills():
    clock = Clock(1000.0)
    bus, diag = FakeBus(), FakeDiag()
    rt = make_runtime(bus, diag, clock)

    bus.queue(alarm(ts=1000.0))
    rt.tick()                                   # arms, but must not diagnose yet
    assert diag.calls == []
    assert bus.published == []

    clock.advance(10)                           # onset+10, window (30s) not full
    rt.tick()
    assert bus.published == []

    clock.advance(30)                           # now past onset+30+margin
    rt.tick()
    assert len(diag.calls) == 1
    assert len(bus.published) == 1

    # the published payload is a well-formed Diagnosis carrying the match
    d = Diagnosis.model_validate_json(bus.published[0])
    assert d.trigger_tag == "REACTOR.T" and d.trigger_level == "HH"
    assert d.matches[0].cause_id == "IDV-4"
    assert d.graph_version == 7


# --- coalescing -------------------------------------------------------------
def test_a_burst_of_alarms_becomes_one_diagnosis():
    clock = Clock(1000.0)
    bus, diag = FakeBus(), FakeDiag()
    rt = make_runtime(bus, diag, clock)

    # one fault trips three tags near-simultaneously
    bus.queue(alarm("REACTOR.T", "HH", 1000.0),
              alarm("REACTOR.P", "HH", 1001.0),
              alarm("SEPARATOR.Level", "LL", 1002.0))
    rt.tick()
    clock.advance(60)
    rt.tick()

    assert len(diag.calls) == 1                 # one episode, one diagnosis
    assert len(bus.published) == 1
    # anchored at the first alarm's onset
    assert rt  # sanity
    assert diag.calls[0][0] == datetime.fromtimestamp(1000.0, tz=timezone.utc)


# --- cooldown ---------------------------------------------------------------
def test_cooldown_blocks_re_arming_then_lifts():
    clock = Clock(1000.0)
    bus, diag = FakeBus(), FakeDiag()
    rt = make_runtime(bus, diag, clock)          # cooldown_s=100

    bus.queue(alarm(ts=1000.0))
    rt.tick()
    clock.advance(60)
    rt.tick()                                    # first diagnosis emitted at t=1060
    assert len(bus.published) == 1

    # a new alarm during cooldown does not arm
    clock.advance(20)                            # t=1080, cooldown until 1160
    bus.queue(alarm(tag="REACTOR.P", ts=1080.0))
    rt.tick()
    clock.advance(60)
    rt.tick()
    assert len(bus.published) == 1               # still just the one

    # once cooldown lifts, a fresh alarm arms again
    clock.advance(60)                            # t=1200 > 1160
    bus.queue(alarm(tag="REACTOR.P", ts=1200.0))
    rt.tick()
    clock.advance(60)
    rt.tick()
    assert len(bus.published) == 2


# --- filtering --------------------------------------------------------------
@pytest.mark.parametrize("payload", [
    alarm(kind="compliance"),                    # not a plant breach
    alarm(type_="investigation"),                # our own output
    {"kind": "process_limit"},                   # no tag_id
    {"kind": "failure_pattern", "tag_id": "X"},  # wrong kind
])
def test_non_plant_alarms_never_arm(payload):
    clock = Clock(1000.0)
    bus, diag = FakeBus(), FakeDiag()
    rt = make_runtime(bus, diag, clock)

    bus.queue(payload)
    rt.tick()
    clock.advance(200)
    rt.tick()
    assert diag.calls == [] and bus.published == []


def test_empty_window_consumes_the_episode_without_publishing():
    clock = Clock(1000.0)
    bus, diag = FakeBus(), FakeDiag(result=None)  # historian had nothing
    rt = make_runtime(bus, diag, clock)

    bus.queue(alarm(ts=1000.0))
    rt.tick()
    clock.advance(60)
    rt.tick()

    assert len(diag.calls) == 1                  # it tried
    assert bus.published == []                   # but emitted nothing
    # and it still entered cooldown (episode consumed, not retried in a loop)
    clock.advance(1)
    bus.queue(alarm(ts=1061.0))
    rt.tick()
    assert rt._pending is None                   # cooldown blocked the re-arm


# --- cursor + housekeeping --------------------------------------------------
def test_cursor_advances_over_the_batch():
    clock = Clock(1000.0)
    bus, diag = FakeBus(), FakeDiag()
    rt = make_runtime(bus, diag, clock)

    bus.queue(alarm(ts=1000.0), alarm("REACTOR.P", ts=1001.0))
    rt.tick()
    assert bus.get_cursor("diagnostics-alarms") == "1-0"   # last entry id


def test_seed_cursor_starts_at_the_tail_on_first_run():
    clock = Clock(1000.0)
    bus, diag = FakeBus(), FakeDiag()
    rt = make_runtime(bus, diag, clock)

    # history already on the stream when we first boot
    bus.queue(alarm(ts=900.0), alarm(ts=950.0))
    rt._seed_cursor()
    # cursor jumped to the newest existing id, so that backlog is skipped
    assert bus.get_cursor("diagnostics-alarms") == "1-0"

    # a stored (non-"0") cursor is left alone on a restart
    bus.set_cursor("diagnostics-alarms", "5-0")
    bus.queue(alarm(ts=1000.0))
    rt._seed_cursor()
    assert bus.get_cursor("diagnostics-alarms") == "5-0"


def test_refresh_reloads_library_and_tags_on_cadence():
    clock = Clock(1000.0)
    bus, diag = FakeBus(), FakeDiag()
    rt = DiagnosticsRuntime(bus, diag, library_refresh_s=100, clock=clock)

    rt.tick()
    assert diag.reloaded == 0                    # not yet due
    clock.advance(150)
    rt.tick()
    assert diag.reloaded == 1 and diag.tags_refreshed == 1
