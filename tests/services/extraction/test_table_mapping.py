import asyncio
import io

import pytest

from plantmind_core.schemas import NodeType
from extraction.workorder.mapping import MappingInferrer, TableMapping
from extraction.workorder.parser import TableParser
from conftest import FakeLLM

SAP_EXPORT = (
    b"Maint. Order,Asset Code,Damage Code,Created On,Long Text,Closed By,Down Hrs\n"
    b"4711,P-101A,SEAL-LEAK,2026-01-05,Seal weeping at gland,R. Sharma,6.5\n"
    b"4712,K-301,TRIP,2026-02-01,High discharge temp trip,S. Patel,22\n"
)

SAP_MAPPING = TableMapping(
    kind="work_orders", wo_id="Maint. Order", equipment_tag="Asset Code",
    failure_code="Damage Code", date="Created On", description="Long Text",
    technician="Closed By", downtime_hours="Down Hrs",
)


def test_known_headers_map_by_rule_without_llm():
    inferrer = MappingInferrer(llm=None)   # would raise if the llm were needed

    mapping = asyncio.run(inferrer.infer(
        ["wo_id", "equipment_tag", "failure_code", "date"], []))

    assert mapping.kind == "work_orders"
    assert mapping.wo_id == "wo_id"
    assert mapping.downtime_hours == ""    # absent column stays unmapped


def test_alien_headers_resolved_by_llm_then_parsed_deterministically():
    llm = FakeLLM(SAP_MAPPING)

    csg = asyncio.run(TableParser(llm).parse("doc-sap", "h", "export.csv",
                                             SAP_EXPORT))

    wos = [n for n in csg.nodes if n.type == NodeType.WORK_ORDER]
    assert {n.surface_form for n in wos} == {"4711", "4712"}
    wo = next(n for n in wos if n.surface_form == "4711")
    assert wo.props["technician"] == "R. Sharma"
    assert wo.props["downtime_hours"] == 6.5

    tags = {n.surface_form for n in csg.nodes if n.type == NodeType.EQUIPMENT}
    assert tags == {"P-101A", "K-301"}

    assert len(llm.calls) == 1             # one mapping call for the whole file


def test_mapping_with_phantom_header_rejected():
    bad = TableMapping(kind="work_orders", wo_id="Order No",   # not in headers
                       equipment_tag="Asset Code", failure_code="Damage Code")

    with pytest.raises(ValueError, match="do not exist"):
        asyncio.run(TableParser(FakeLLM(bad)).parse("d", "h", "x.csv", SAP_EXPORT))


def test_unknown_kind_rejected():
    with pytest.raises(ValueError, match="not recognisable"):
        asyncio.run(TableParser(FakeLLM(TableMapping(kind="unknown")))
                    .parse("d", "h", "x.csv", SAP_EXPORT))


def test_missing_required_field_rejected():
    incomplete = TableMapping(kind="work_orders", wo_id="Maint. Order")

    with pytest.raises(ValueError, match="required fields"):
        asyncio.run(TableParser(FakeLLM(incomplete)).parse("d", "h", "x.csv",
                                                           SAP_EXPORT))


def test_excel_workbook_parses_like_csv():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["wo_id", "equipment_tag", "failure_code", "downtime_hours"])
    ws.append(["WO-9001", "P-101A", "SEAL-LEAK", 4])
    ws.append(["WO-9002", "E-204", "FOULING", None])
    buf = io.BytesIO()
    wb.save(buf)

    csg = asyncio.run(TableParser().parse("doc-xl", "h", "orders.xlsx",
                                          buf.getvalue()))

    wos = {n.surface_form for n in csg.nodes if n.type == NodeType.WORK_ORDER}
    assert wos == {"WO-9001", "WO-9002"}
    wo = next(n for n in csg.nodes if n.surface_form == "WO-9001")
    assert wo.props["downtime_hours"] == 4.0
