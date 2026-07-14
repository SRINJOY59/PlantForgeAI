import asyncio

import pytest

from plantmind_core.schemas import EdgeType, NodeType
from extraction.workorder.parser import TableParser
from conftest import SAMPLES


def parse(filename, data, doc_id="doc-x", llm=None):
    return asyncio.run(TableParser(llm).parse(doc_id, "hash-x", filename, data))


def nodes_of(csg, node_type):
    return [n for n in csg.nodes if n.type == node_type]


def edges_of(csg, edge_type):
    return [e for e in csg.edges if e.type == edge_type]


def test_work_orders_sample_parses_completely():
    csg = parse("work_orders.csv", (SAMPLES / "work_orders.csv").read_bytes())

    assert len(nodes_of(csg, NodeType.WORK_ORDER)) == 12       # one per row
    assert len(nodes_of(csg, NodeType.DOCUMENT)) == 1

    tags = {n.surface_form for n in nodes_of(csg, NodeType.EQUIPMENT)}
    assert tags == {"P-101A", "P-101B", "E-204", "V-203", "K-301",
                    "PSV-204", "FT-103"}

    failures = {n.surface_form for n in nodes_of(csg, NodeType.FAILURE_MODE)}
    assert "SEAL-LEAK" in failures and "TRIP" in failures

    seal_leaks = [e for e in edges_of(csg, EdgeType.HAS_FAILURE)
                  if e.dst == "SEAL-LEAK"]
    assert len(seal_leaks) == 4
    assert {e.src for e in seal_leaks} == {"P-101A", "P-101B"}


def test_work_order_props_carried():
    csg = parse("work_orders.csv", (SAMPLES / "work_orders.csv").read_bytes())

    wo = next(n for n in nodes_of(csg, NodeType.WORK_ORDER)
              if n.surface_form == "WO-2214")
    assert wo.props["technician"] == "R. Sharma"
    assert wo.props["downtime_hours"] == 9.0
    assert "PI-102" in wo.props["description"]


def test_provenance_points_at_source_row():
    csg = parse("work_orders.csv", (SAMPLES / "work_orders.csv").read_bytes())

    first_failure = edges_of(csg, EdgeType.HAS_FAILURE)[0]
    assert first_failure.provenance.doc_id == "doc-x"
    assert first_failure.provenance.page == 1                  # row number
    assert first_failure.provenance.confidence == 1.0


def test_inspections_sample_builds_compliance_edges():
    csg = parse("inspection_records.csv",
                (SAMPLES / "inspection_records.csv").read_bytes())

    standards = {n.surface_form for n in nodes_of(csg, NodeType.REGULATION_CLAUSE)}
    assert "OISD-STD-128" in standards
    assert "OISD-STD-119" in standards

    governed = edges_of(csg, EdgeType.GOVERNED_BY)
    v203 = next(e for e in governed if e.src == "V-203")
    assert v203.dst == "OISD-STD-128"
    assert v203.props["next_due"] == "2026-02-10"              # the overdue one
    assert v203.props["inspection_type"] == "Hydrostatic test"


def test_no_resolved_ids_yet():
    csg = parse("work_orders.csv", (SAMPLES / "work_orders.csv").read_bytes())
    assert all(n.resolved_id is None for n in csg.nodes)       # resolver's job


def test_unknown_table_without_llm_rejected():
    with pytest.raises(ValueError, match="no LLM wired"):
        parse("mystery.csv", b"a,b,c\n1,2,3\n")


def test_empty_file_rejected():
    with pytest.raises(ValueError, match="no data rows"):
        parse("empty.csv", b"wo_id,date\n")
