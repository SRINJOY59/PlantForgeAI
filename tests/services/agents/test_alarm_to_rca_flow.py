"""Simulator alarm -> alert -> investigation, end to end over one redis.

The pieces of this path each had their own tests and the path itself had none,
which is how it came to be broken in three places at once: the watcher stopped
re-arming, the runtime routed its own output back into the RCA handler, and
every investigation after the first died on a closed event loop. Each fault
alone is enough to make an operator report "the alerts and the RCA are not
working", and none of them fails a unit test of the component it lives in.
"""

import json

import fakeredis
import pytest

from plantmind_core.bus import RedisBus
from plantmind_core.schemas import Alert, Citation

from agents.consumer import AgentsRuntime
from agents.watchers.tep import DEBOUNCE_S, TepWatcher
from conftest import FakeAgentReader


class RecordingInvestigator:
    """Stands in for the LLM. Counts calls, so a silently-skipped
    investigation is a failed assertion rather than a quiet nothing."""

    def __init__(self):
        self.calls = []

    async def investigate_reasoned(self, trigger, alert_context=None):
        self.calls.append((trigger, alert_context))
        alert = Alert(
            kind="failure_pattern", severity="critical",
            title=f"{trigger.tag} {trigger.mode}",
            body=f"root cause for {trigger.tag}", equipment=trigger.tag,
            citations=[Citation(doc_id="d1", snippet="")],
            fingerprint=f"failure:{trigger.tag}:{trigger.mode}:1")
        return alert, None


@pytest.fixture
def plant(monkeypatch):
    """One redis shared by the watcher and the runtime, as in the deployment."""
    r = fakeredis.FakeRedis(decode_responses=True)
    bus = RedisBus(r)

    watcher = TepWatcher(RedisBus(r))
    watcher._envelopes = {"REACTOR.T": {"ll": 100.0, "l": 110.0,
                                        "setpoint": 122.9, "h": 135.0,
                                        "hh": 145.0}}

    inv = RecordingInvestigator()
    # this suite exercises the auto-RCA path itself, which is opt-in now
    runtime = AgentsRuntime(bus, FakeAgentReader(), investigator=inv,
                            compliance_interval=10_000, block_ms=0,
                            auto_rca=True)

    # the handler asks the simulator which IDVs are active; there is no
    # simulator here, and the handler is meant to carry on without one
    async def no_sim(*a, **k):
        raise OSError("no simulator in this test")
    monkeypatch.setattr("httpx.AsyncClient.get", no_sim)

    return bus, watcher, runtime, inv


def investigations(bus):
    return [json.loads(p) for _, p in bus.read_alerts(block_ms=0)
            if json.loads(p).get("type") == "investigation"]


def test_a_breach_produces_an_alert_and_an_investigation(plant):
    bus, watcher, runtime, inv = plant

    watcher._check_message({"tag_id": "REACTOR.T", "value": "150.0"})
    runtime.tick_alarms()

    assert len(inv.calls) == 1
    _, context = inv.calls[0]
    assert context["tag_id"] == "REACTOR.T" and context["alarm_level"] == "HH"
    assert context["active_idvs"] == []          # simulator unreachable, not fatal

    published = investigations(bus)
    assert len(published) == 1
    assert published[0]["tag_id"] == "REACTOR.T"
    assert "root cause" in published[0]["summary"]


def test_a_second_incident_is_investigated_too(plant, monkeypatch):
    """The reported symptom, in one test: inject, clear, inject again.

    This failed on every one of the three faults independently - no second
    alert from the watcher, the alert suppressed by a fingerprint cooldown in
    the handler, or the investigation itself dying on a closed event loop.
    """
    bus, watcher, runtime, inv = plant
    now = [1000.0]
    monkeypatch.setattr("agents.watchers.tep.time.time", lambda: now[0])

    watcher._check_message({"tag_id": "REACTOR.T", "value": "150.0"})
    runtime.tick_alarms()
    assert len(inv.calls) == 1

    # operator clears the fault; the tag settles back inside its envelope
    watcher._check_message({"tag_id": "REACTOR.T", "value": "122.9"})
    now[0] += DEBOUNCE_S + 1
    watcher._check_message({"tag_id": "REACTOR.T", "value": "122.9"})

    # and injects it again
    watcher._check_message({"tag_id": "REACTOR.T", "value": "150.0"})
    runtime.tick_alarms()

    assert len(inv.calls) == 2, "second incident got no investigation"
    assert len(investigations(bus)) == 2


def test_the_runtime_does_not_investigate_its_own_investigations(plant):
    """Everything the runtime publishes lands back on the stream it reads."""
    bus, watcher, runtime, inv = plant

    watcher._check_message({"tag_id": "REACTOR.T", "value": "150.0"})
    runtime.tick_alarms()
    runtime.tick_alarms()          # the investigation is now on the stream
    runtime.tick_alarms()

    assert len(inv.calls) == 1


def test_a_compliance_sweep_does_not_burn_an_llm_call(plant):
    bus, _, runtime, inv = plant
    runtime._emit([Alert(kind="compliance", severity="warning",
                         title="Overdue inspection: V-203", body="overdue",
                         equipment="V-203", fingerprint="compliance:V-203")])

    runtime.tick_alarms()

    assert inv.calls == []
    kinds = [json.loads(p).get("kind") for _, p in bus.read_alerts(block_ms=0)]
    assert kinds == ["compliance"]
