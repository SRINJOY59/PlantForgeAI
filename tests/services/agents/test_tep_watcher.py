"""The TEP threshold watcher's alarm lifecycle.

These exist because the watcher's job is not "notice a breach" - it noticed the
first one fine - but "be ready to notice the next one". Every test here is
about re-arming.
"""

import json

import fakeredis
import pytest

from plantmind_core.bus import RedisBus
from agents.watchers.tep import DEBOUNCE_S, TepWatcher


@pytest.fixture
def watcher():
    w = TepWatcher(RedisBus(fakeredis.FakeRedis(decode_responses=True)))
    w._envelopes = {"REACTOR.T": {"ll": 100.0, "l": 110.0, "setpoint": 122.9,
                                  "h": 135.0, "hh": 145.0}}
    return w


def fired(w):
    return [json.loads(f["payload"])
            for _, f in w._bus._r.xrange("alerts:critical")]


def sample(w, value, tag="REACTOR.T"):
    w._check_message({"tag_id": tag, "value": str(value)})


def test_breach_fires_once_while_it_persists(watcher):
    for _ in range(5):
        sample(watcher, 140.0)
    assert len(fired(watcher)) == 1
    assert fired(watcher)[0]["level"] == "H"


def test_alarm_rearms_after_recovery_and_fires_again(watcher, monkeypatch):
    """The regression this file exists for.

    Open alarms used to be keyed by tag+level, and the return-to-normal branch
    had no level to build that key with - so it looked up "<tag>:None", never
    matched, and left the alarm open forever. The operator cleared the fault,
    injected it again, and got silence: the second incident produced no alert
    and therefore no investigation.
    """
    now = [1000.0]
    monkeypatch.setattr("agents.watchers.tep.time.time", lambda: now[0])

    sample(watcher, 140.0)
    assert len(fired(watcher)) == 1

    # back inside the envelope, and stays there past the debounce
    sample(watcher, 122.9)
    now[0] += DEBOUNCE_S + 1
    sample(watcher, 122.9)
    assert watcher._open == {}, "alarm should have re-armed"

    sample(watcher, 140.0)
    assert len(fired(watcher)) == 2


def test_brief_dip_inside_the_envelope_does_not_rearm(watcher, monkeypatch):
    """A tag chattering across its limit is one alarm, not one per crossing."""
    now = [1000.0]
    monkeypatch.setattr("agents.watchers.tep.time.time", lambda: now[0])

    sample(watcher, 140.0)
    now[0] += 1
    sample(watcher, 130.0)          # dips in, well short of the debounce
    now[0] += 1
    sample(watcher, 140.0)          # and straight back out

    assert len(fired(watcher)) == 1


def test_escalation_to_a_higher_level_fires_again(watcher):
    sample(watcher, 140.0)          # H
    sample(watcher, 150.0)          # HH - a different, worse alarm
    levels = [a["level"] for a in fired(watcher)]
    assert levels == ["H", "HH"]


def test_rearm_all_clears_open_alarms(watcher):
    """Reset drops every PV back to nominal in one step, so the watcher never
    sees the in-envelope samples that would clear its open alarms. Without the
    reset announcement, the fault injected after a reset alarms into a
    suppressed state and the operator sees nothing."""
    sample(watcher, 140.0)
    assert watcher._open

    watcher.rearm_all("simulator reset")
    assert watcher._open == {}

    sample(watcher, 140.0)
    assert len(fired(watcher)) == 2


def test_unknown_tag_and_unparseable_value_are_ignored(watcher):
    watcher._check_message({"tag_id": "NOT.A.TAG", "value": "999"})
    watcher._check_message({"tag_id": "REACTOR.T", "value": "n/a"})
    assert fired(watcher) == []


def test_actuator_tags_never_alarm(watcher):
    """A control valve at 100% is the controller working, not a breach. MV.*
    tags are skipped even if an envelope is still configured for them."""
    watcher._envelopes["MV.REACTOR-COOL"] = {"ll": 0.0, "l": 10.0, "h": 90.0,
                                             "hh": 100.0, "setpoint": 50.0}
    for _ in range(5):
        sample(watcher, 100.0, tag="MV.REACTOR-COOL")   # valve fully open
    assert fired(watcher) == []
