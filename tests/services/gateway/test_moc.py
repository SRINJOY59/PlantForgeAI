"""The gateway does no MOC thinking - it forwards to the agents service and
relays. What is worth pinning here is that it forwards to the *right* upstream
and does not quietly answer for it."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway.deps import get_agents_http, get_service
from gateway.main import app
from gateway.service import GatewayService
from conftest import FakeBus, FakeSender, FakeStore

PROPOSAL = {"tag": "P-101A", "summary": "replace mechanical seal",
            "proposed_by": "eng@plant.com"}

ASSESSMENT = {
    "proposal": PROPOSAL, "body": "Governed by OISD-STD-119.",
    "affected_equipment": ["PI-102"], "documents_to_revise": ["sop-101.md"],
    "governing_clauses": ["OISD-STD-119"], "citations": [],
    "graph_version": 12, "verified": True, "unverified_claims": [],
}


def fake_agents(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler),
                             base_url="http://agents-api:8002")


@pytest.fixture
def client():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ASSESSMENT)

    app.dependency_overrides[get_agents_http] = lambda: fake_agents(handler)
    # the rate-limit dependency on /moc/assess reads the bus through get_service
    app.dependency_overrides[get_service] = lambda: GatewayService(
        FakeStore(), FakeBus(), FakeSender())
    yield TestClient(app), seen
    app.dependency_overrides.clear()


def test_proposal_is_forwarded_to_the_agents_service(client):
    c, seen = client
    resp = c.post("/moc/assess", json=PROPOSAL)

    assert resp.status_code == 200
    # not retrieval - an assessment is not a question
    assert seen["url"] == "http://agents-api:8002/assess"
    assert seen["body"]["tag"] == "P-101A"


def test_assessment_is_relayed_unchanged(client):
    c, _ = client
    body = c.post("/moc/assess", json=PROPOSAL).json()

    assert body["governing_clauses"] == ["OISD-STD-119"]
    assert body["documents_to_revise"] == ["sop-101.md"]
    assert body["graph_version"] == 12
    assert "verdict" not in body


def test_a_proposal_without_a_tag_is_rejected_at_the_edge(client):
    c, seen = client
    resp = c.post("/moc/assess", json={"summary": "replace the seal"})

    assert resp.status_code == 422
    assert seen == {}          # never reached the agents service


def test_upstream_failure_is_relayed_not_masked():
    def handler(request):
        return httpx.Response(503, json={"detail": "graph unreachable"})

    app.dependency_overrides[get_agents_http] = lambda: fake_agents(handler)
    app.dependency_overrides[get_service] = lambda: GatewayService(
        FakeStore(), FakeBus(), FakeSender())
    try:
        resp = TestClient(app).post("/moc/assess", json=PROPOSAL)
        # an assessment that failed must not look like one that found nothing
        assert resp.status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_both_moc_routes_are_registered():
    # the relay body is byte-identical to qa.ask_stream, which is already
    # proven; httpx MockTransport can't model a streaming upstream, so the
    # frame-for-frame proof is the live end-to-end run, not this mock. Here we
    # only pin that both routes exist to be reached.
    paths = app.openapi()["paths"]
    assert "/moc/assess" in paths
    assert "/moc/assess/stream" in paths
