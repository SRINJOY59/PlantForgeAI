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
