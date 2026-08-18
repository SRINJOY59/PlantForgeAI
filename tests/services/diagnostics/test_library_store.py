"""The FaultLibraryStore - the translation between a FaultSignature and its
life as a node in the graph.

No live Neo4j: a fake driver records every Cypher call and its parameters, so
the two things that actually matter can be pinned - that the node is shaped the
way the readers expect (the signature travels whole as JSON, the flat filter
columns are present), and that a stored FaultMode round-trips back to an equal
one. The Cypher text itself is not asserted; the property shapes and the edges
that get written are.
"""

from datetime import datetime, timedelta, timezone

import pytest

from plantmind_core.schemas import (
    FaultMode, FaultSignature, TagDeviation, NodeType, EdgeType,
)
from diagnostics.library.store import FaultLibraryStore


# --- a fake neo4j driver that records calls --------------------------------
class FakeTx:
    def __init__(self, read_rows=None):
        self.calls = []                 # (query, kwargs) for every run()
        self._read_rows = read_rows or []

    def run(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return list(self._read_rows)    # only the read path iterates the result


class FakeSession:
    def __init__(self, tx):
        self._tx = tx

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute_write(self, fn, *args):
        return fn(self._tx, *args)

    def execute_read(self, fn, *args):
        return fn(self._tx, *args)


class FakeDriver:
    def __init__(self, read_rows=None):
        self.tx = FakeTx(read_rows)
        self.closed = False

    def session(self):
        return FakeSession(self.tx)

    def close(self):
        self.closed = True


# --- fixtures ---------------------------------------------------------------
T0 = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


def make_signature():
    return FaultSignature(
        deviations=[
            TagDeviation(tag_id="REACTOR.T", direction="high", magnitude=18.0,
                         onset_offset_s=2.0, first_mover_rank=0),
            TagDeviation(tag_id="SEPARATOR.Level", direction="low", magnitude=7.5,
                         onset_offset_s=15.0, first_mover_rank=1),
        ],
        window_s=360.0, severity="critical", source="sim",
        cause_id="IDV-4", cause_label="reactor coolant step",
    )


def make_fault_mode(procedure_id="sop:TEP-REACTOR-T-HIGH"):
    return FaultMode(
        id="faultmode:IDV-4",
        cause_id="IDV-4",
        cause_label="reactor coolant step",
        unit_areas=["REACTOR", "SEPARATOR"],
        signature=make_signature(),
        procedure_id=procedure_id,
    )


# --- writes -----------------------------------------------------------------
def test_store_writes_node_edges_and_procedure():
    driver = FakeDriver()
    store = FaultLibraryStore(driver)
    store.store(make_fault_mode())

    calls = driver.tx.calls
    # 1 node merge + 2 equipment edges + 1 procedure edge
    assert len(calls) == 4

    node_q, node_p = calls[0]
    assert NodeType.FAULT_MODE.value in node_q       # labelled :FaultMode
    props = node_p["props"]
    assert props["id"] == "faultmode:IDV-4"
    assert props["deviation_tags"] == ["REACTOR.T", "SEPARATOR.Level"]
    assert props["lead_tag"] == "REACTOR.T"          # the first mover
    assert props["unit_areas"] == ["REACTOR", "SEPARATOR"]
    assert props["severity"] == "critical"

    # the whole signature travels as JSON and rehydrates unchanged
    rehydrated = FaultSignature.model_validate_json(props["signature_json"])
    assert len(rehydrated.deviations) == 2
    assert rehydrated.deviations[0].tag_id == "REACTOR.T"

    # one EXHIBITS_FAULT per area, from the seeded equipment
    edge_calls = [c for c in calls if EdgeType.EXHIBITS_FAULT.value in c[0]]
    assert {c[1]["area"] for c in edge_calls} == {"REACTOR", "SEPARATOR"}

    # the procedure edge is present
    resp_calls = [c for c in calls if EdgeType.RESPONDS_WITH.value in c[0]]
    assert len(resp_calls) == 1
    assert resp_calls[0][1]["pid"] == "sop:TEP-REACTOR-T-HIGH"


def test_store_without_procedure_writes_no_responds_edge():
    driver = FakeDriver()
    FaultLibraryStore(driver).store(make_fault_mode(procedure_id=None))

    resp_calls = [c for c in driver.tx.calls
                  if EdgeType.RESPONDS_WITH.value in c[0]]
    assert resp_calls == []


def test_store_with_no_deviations_leaves_lead_tag_empty():
    driver = FakeDriver()
    fm = make_fault_mode()
    fm.signature.deviations = []
    FaultLibraryStore(driver).store(fm)

    props = driver.tx.calls[0][1]["props"]
    assert props["lead_tag"] == ""
    assert props["deviation_tags"] == []


# --- reads ------------------------------------------------------------------
def test_all_rehydrates_stored_fault_modes():
    row = {
        "id": "faultmode:IDV-4",
        "cause_id": "IDV-4",
        "cause_label": "reactor coolant step",
        "unit_areas": ["REACTOR", "SEPARATOR"],
        "signature_json": make_signature().model_dump_json(),
        "procedure_id": "sop:TEP-REACTOR-T-HIGH",
    }
    store = FaultLibraryStore(FakeDriver(read_rows=[row]))
    modes = store.all()

    assert len(modes) == 1
    fm = modes[0]
    assert isinstance(fm, FaultMode)
    assert fm.id == "faultmode:IDV-4"
    assert fm.procedure_id == "sop:TEP-REACTOR-T-HIGH"
    assert len(fm.signature.deviations) == 2
    assert fm.signature.deviations[0].tag_id == "REACTOR.T"


def test_all_skips_a_row_with_unreadable_signature():
    good = {
        "id": "faultmode:IDV-4", "cause_id": "IDV-4",
        "cause_label": "", "unit_areas": [],
        "signature_json": make_signature().model_dump_json(),
        "procedure_id": None,
    }
    bad = {**good, "id": "faultmode:IDV-9", "signature_json": "{not json"}
    missing = {**good, "id": "faultmode:IDV-2", "signature_json": None}

    store = FaultLibraryStore(FakeDriver(read_rows=[good, bad, missing]))
    modes = store.all()

    # the two malformed rows are dropped, not fatal
    assert [m.id for m in modes] == ["faultmode:IDV-4"]


def test_close_closes_the_driver():
    driver = FakeDriver()
    FaultLibraryStore(driver).close()
    assert driver.closed is True
