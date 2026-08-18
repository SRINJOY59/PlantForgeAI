import json

import fakeredis

from plantmind_core.bus import RedisBus
from plantmind_core.schemas import Alert, Citation, GraphDelta

from agents.consumer import CURSOR, AgentsRuntime
from conftest import FakeAgentReader


class StubInvestigator:
    """Skips the LLM: turns a trigger straight into an alert."""

    def __init__(self):
        self.calls = []

    async def investigate(self, trigger):
        self.calls.append(trigger)
        return Alert(kind="failure_pattern", severity="warning",
                     title=f"{trigger.tag} {trigger.mode}", body="investigated",
                     equipment=trigger.tag,
                     fingerprint=f"failure:{trigger.tag}:{trigger.mode}:"
                                 f"{trigger.count}",
                     graph_version=trigger.graph_version)

    async def investigate_reasoned(self, trigger):
        """The consumer drafts a work order off the investigation trace, so the
        double has to hand back a trace as well as the alert. Empty here: these
        tests are about the alert path, and a drafter with nothing to harvest
        still produces a valid (if bare) draft."""
        return await self.investigate(trigger), _Reasoned()


class _Reasoned:
    """Stands in for agents.usecases.base.Reasoned - only the fields the
    work-order drafter reads."""
    answer = "investigated"
    trace = []
    docs = []
    grounding = None


def seal_leak_reader():
    r = FakeAgentReader()
    r.failures["equip:P-101B"] = [
        {"tag": "P-101B", "mode": "SEAL-LEAK", "count": 1,
         "causes": [], "docs": ["d"]}]
    r.family[("P-101", "SEAL-LEAK")] = [
        {"tag": "P-101A", "count": 3, "causes": ["cavitation"], "docs": ["d"]}]
    return r


def runtime(reader):
    bus = RedisBus(fakeredis.FakeRedis(decode_responses=True))
    inv = StubInvestigator()
    return bus, inv, AgentsRuntime(bus, reader, investigator=inv,
                                   compliance_interval=10_000, block_ms=0)


def alerts_on(bus):
    return [Alert.model_validate_json(p) for _, p in bus.read_alerts(block_ms=0)]


def failure_delta():
    return GraphDelta(graph_version=5, touched_node_ids=["equip:P-101B"],
                      new_edge_types=["HAS_FAILURE"],
                      source_doc_ids=["d"]).model_dump_json()


def test_failure_delta_triggers_investigation_and_alert():
    bus, inv, rt = runtime(seal_leak_reader())
    bus.publish_delta(failure_delta())

    rt.tick()

    assert len(inv.calls) == 1 and inv.calls[0].tag == "P-101B"
    published = alerts_on(bus)
    assert len(published) == 1 and published[0].equipment == "P-101B"


def test_delta_without_failure_edge_ignored():
    bus, inv, rt = runtime(seal_leak_reader())
    bus.publish_delta(GraphDelta(
        graph_version=5, touched_node_ids=["equip:P-101B"],
        new_edge_types=["MENTIONED_IN"], source_doc_ids=["d"]).model_dump_json())

    rt.tick()
    assert inv.calls == [] and alerts_on(bus) == []


def test_same_pattern_investigated_once():
    bus, inv, rt = runtime(seal_leak_reader())
    bus.publish_delta(failure_delta())
    rt.tick()
    bus.publish_delta(failure_delta())
    rt.tick()

    assert len(inv.calls) == 1          # claim_alert dedupe stops re-investigation
    assert len(alerts_on(bus)) == 1


def test_emit_names_citations_so_the_ui_can_open_them():
    reader = seal_leak_reader()
    reader.names = {"inspection_records.csv": "inspection_records.csv",
                    "6d6d71a9e053a1bd": "sop_pump_seal_replacement.md"}
    bus, _, rt = runtime(reader)

    alert = Alert(
        kind="compliance", severity="warning", title="Overdue: V-203",
        body="overdue", fingerprint="compliance:V-203",
        citations=[Citation(doc_id="6d6d71a9e053a1bd", snippet=""),
                   Citation(doc_id="unknown-hash", snippet="")])
    rt._emit([alert])

    published = alerts_on(bus)[0]
    by_id = {c.doc_id: c.filename for c in published.citations}
    # the hash resolves to a name; an unknown doc degrades to no name, not a crash
    assert by_id["6d6d71a9e053a1bd"] == "sop_pump_seal_replacement.md"
    assert by_id["unknown-hash"] is None


def test_cursor_advances():
    bus, _, rt = runtime(seal_leak_reader())
    bus.publish_delta(failure_delta())
    rt.tick()
    first = bus.get_cursor(CURSOR)
    rt.tick()
    assert bus.get_cursor(CURSOR) == first and first != "0"


def test_startup_compliance_sweep():
    reader = FakeAgentReader()
    reader.overdue = [{"equipment": "V-203", "standard": "OISD-STD-128",
                       "inspection_type": "Hydro", "next_due": "2026-02-10",
                       "doc_id": "ins", "page": 1}]
    bus, _, rt = runtime(reader)

    rt.run_compliance()

    published = alerts_on(bus)
    assert len(published) == 1 and published[0].kind == "compliance"


# --- alarm routing -------------------------------------------------------
# The runtime reads alerts:critical and also publishes onto it, so the routing
# rule is what keeps it from investigating its own output. It used to select on
# severity, and every alert this runtime writes is warning or critical.

def tep_alarm_payload(**over):
    p = {"kind": "process_limit", "severity": "critical", "tag_id": "REACTOR.T",
         "unit": "REACTOR", "equipment": "REACTOR", "level": "HH",
         "value": 150.0, "limit": 145.0, "fingerprint": "tep:REACTOR.T:HH"}
    p.update(over)
    return json.dumps(p)


def route(rt, payload):
    """The routed coroutine, closed if there is one - these tests are about
    which handler is chosen, not what it does, and an un-awaited coroutine
    warns."""
    coro = rt._route_alarm("1-0", payload)
    if coro is not None:
        coro.close()
    return coro


def test_tep_alarm_routes_to_the_tep_handler():
    _, _, rt = runtime(seal_leak_reader())
    assert route(rt, tep_alarm_payload()) is not None


def test_watcher_alarm_with_a_rule_routes_to_the_process_limit_handler(monkeypatch):
    _, _, rt = runtime(seal_leak_reader())
    seen = []
    monkeypatch.setattr(rt._process_limit_handler, "handle_process_limit",
                        lambda entry_id, payload: seen.append(payload) or None)
    rt._route_alarm("1-0", json.dumps(
        {"kind": "process_limit", "severity": "warning", "tag_id": "CSTR.T",
         "equipment": "CSTR-101", "rule": "T_HIGH"}))
    assert len(seen) == 1 and seen[0]["rule"] == "T_HIGH"


def test_compliance_alert_is_not_investigated_as_a_process_alarm():
    """An overdue inspection is warning severity and has no tag. Routed on
    severity it reached the TEP alarm handler, spent an LLM call on an empty
    unit area, and published an investigation of nothing."""
    _, _, rt = runtime(seal_leak_reader())
    alert = Alert(kind="compliance", severity="warning", title="Overdue: V-203",
                  body="overdue", fingerprint="compliance:V-203")
    assert route(rt, alert.model_dump_json()) is None


def test_failure_pattern_alert_is_not_reinvestigated():
    _, _, rt = runtime(seal_leak_reader())
    alert = Alert(kind="failure_pattern", severity="critical",
                  title="P-101B SEAL-LEAK", body="investigated",
                  fingerprint="failure:P-101B:SEAL-LEAK:1")
    assert route(rt, alert.model_dump_json()) is None


def test_investigation_is_not_investigated():
    _, _, rt = runtime(seal_leak_reader())
    assert route(rt, json.dumps(
        {"type": "investigation", "kind": "process_limit",
         "tag_id": "REACTOR.T", "summary": "..."})) is None


def test_malformed_payload_is_skipped_not_raised():
    _, _, rt = runtime(seal_leak_reader())
    assert route(rt, "{not json") is None
    assert route(rt, None) is None


def test_alarm_cursor_advances_over_uninvestigated_entries():
    """Entries this runtime has no handler for are finished with, not deferred -
    otherwise a stream of compliance alerts parks the cursor forever and the
    process alarms behind them are never read."""
    bus, _, rt = runtime(seal_leak_reader())
    bus.publish_alert(Alert(kind="compliance", severity="warning",
                            title="Overdue: V-203", body="overdue",
                            fingerprint="compliance:V-203").model_dump_json())
    rt.tick_alarms()
    assert bus.get_cursor("agents-tep-alerts-cursor") not in ("0", "0-0")


# --- claim lapsing -------------------------------------------------------

def test_swept_alerts_are_re_raised_once_the_claim_lapses():
    """An overdue inspection is a condition, not an event: it is still true on
    the next sweep. A permanent claim announced it once and then never again."""
    bus, _, _ = runtime(seal_leak_reader())
    assert bus.claim_alert("compliance:V-203", ttl_seconds=60) is True
    assert bus.claim_alert("compliance:V-203", ttl_seconds=60) is False

    bus._r.delete("agents:alerted:compliance:V-203")      # the TTL, expired
    assert bus.claim_alert("compliance:V-203", ttl_seconds=60) is True


def test_untimed_claims_are_still_permanent():
    bus, _, _ = runtime(seal_leak_reader())
    assert bus.claim_alert("failure:P-101B:SEAL-LEAK:1") is True
    assert bus.claim_alert("failure:P-101B:SEAL-LEAK:1") is False
