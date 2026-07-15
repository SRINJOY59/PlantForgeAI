"""Exercises the FastAPI surface with the service dependency overridden -
routing, upload handling and document serving, without redis/minio."""

from fastapi.testclient import TestClient

from gateway.deps import get_service
from gateway.main import app
from gateway.service import GatewayService
from conftest import FakeBus, FakeSender, FakeStore


def client_with(docs=None):
    svc = GatewayService(FakeStore(docs), FakeBus(), FakeSender())
    app.dependency_overrides[get_service] = lambda: svc
    return TestClient(app), svc


def teardown_function():
    app.dependency_overrides.clear()


def test_ingest_endpoint_accepts_file():
    client, svc = client_with()

    resp = client.post("/ingest",
                       files={"file": ("orders.csv", b"a,b\n1,2\n", "text/csv")})

    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert svc._send.sent                # a classify note was enqueued


def test_document_endpoint_serves_bytes():
    client, _ = client_with(docs={"abc": ("sop.md", b"# Seal SOP")})

    resp = client.get("/documents/abc")

    assert resp.status_code == 200
    assert resp.content == b"# Seal SOP"
    assert "sop.md" in resp.headers["content-disposition"]


def test_document_endpoint_404_when_missing():
    client, _ = client_with()
    assert client.get("/documents/nope").status_code == 404


def test_metrics_endpoint():
    client, _ = client_with()
    assert client.get("/metrics").json()["graph_version"] == 7


def test_health():
    client, _ = client_with()
    assert client.get("/health").json() == {"status": "ok"}
