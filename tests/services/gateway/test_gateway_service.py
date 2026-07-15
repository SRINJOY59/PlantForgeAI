from plantmind_core.queues import Flow

from gateway.service import GatewayService
from conftest import FakeBus, FakeSender, FakeStore


def make(docs=None):
    store = FakeStore(docs)
    bus = FakeBus()
    sender = FakeSender()
    return GatewayService(store, bus, sender), store, bus, sender


def test_ingest_stages_bytes_and_enqueues_classify():
    svc, store, _, sender = make()

    result = svc.ingest("report.pdf", b"%PDF data", source="upload")

    assert result == {"status": "accepted", "filename": "report.pdf"}
    (staging_key, data), = store.staged.items()
    assert staging_key.startswith("staging/") and staging_key.endswith("report.pdf")
    assert data == b"%PDF data"

    route, payload = sender.sent[0]
    assert route is Flow.ingest
    assert payload["staging_key"] == staging_key
    assert payload["filename"] == "report.pdf"


def test_document_lookup_returns_source():
    svc, *_ = make(docs={"abc123": ("sop.md", b"# SOP")})

    assert svc.document("abc123") == ("sop.md", b"# SOP")
    assert svc.document("missing") is None


def test_metrics_reports_version_and_queues():
    svc, _, bus, _ = make()

    m = svc.metrics()
    assert m["graph_version"] == 7
    assert "q_classify" in m["queues"]
