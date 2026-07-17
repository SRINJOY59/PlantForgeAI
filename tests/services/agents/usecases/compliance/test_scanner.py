from agents.usecases.compliance import ComplianceScanner
from conftest import FakeAgentReader


def test_compliance_scan_flags_overdue():
    reader = FakeAgentReader()
    reader.overdue = [{
        "equipment": "V-203", "standard": "OISD-STD-128",
        "inspection_type": "Hydrostatic test", "next_due": "2026-02-10",
        "doc_id": "ins", "page": 1}]

    alerts = ComplianceScanner(reader).scan("2026-07-15", graph_version=7)

    assert len(alerts) == 1
    a = alerts[0]
    assert a.kind == "compliance" and "V-203" in a.title
    assert "2026-02-10" in a.body
    assert a.citations[0].doc_id == "ins"
    assert a.fingerprint == "compliance:V-203:OISD-STD-128:2026-02-10"


def test_compliance_clean_when_nothing_overdue():
    assert ComplianceScanner(FakeAgentReader()).scan("2026-07-15", 1) == []
