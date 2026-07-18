"""The two abuse surfaces that reach paid work or a parser: expensive LLM
endpoints, and the upload gate."""

import io

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway.deps import get_agents_http, get_http, get_service
from gateway.main import app
from gateway.ratelimit import LIMITS
from gateway.service import GatewayService
from conftest import FakeBus, FakeSender, FakeStore


def _ok_upstream(payload):
    def handler(request):
        return httpx.Response(200, json=payload)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler),
                             base_url="http://upstream")


@pytest.fixture
def parts():
    store, bus, sender = FakeStore(), FakeBus(), FakeSender()
    svc = GatewayService(store, bus, sender)
    app.dependency_overrides[get_service] = lambda: svc
    # the upstreams are faked so an *allowed* call returns 200; the tests only
    # care which calls were let through the meter, not what they returned
    app.dependency_overrides[get_http] = lambda: _ok_upstream(
        {"text": "ok", "citations": []})
    app.dependency_overrides[get_agents_http] = lambda: _ok_upstream(
        {"body": "ok"})
    yield TestClient(app), bus
    app.dependency_overrides.clear()


# -- rate limiting ------------------------------------------------------------
def test_ask_is_capped_and_then_429s(parts):
    client, _ = parts
    limit, _window = LIMITS["ask"]

    # every call over the limit is refused; the upstream is faked, so a 200 here
    # only means "was allowed through", which is all this asserts
    codes = [client.post("/ask", json={"question": "hi"}).status_code
             for _ in range(limit + 2)]
    assert codes.count(429) == 2
    assert codes[-1] == 429


def test_the_429_tells_the_client_when_to_retry(parts):
    client, _ = parts
    limit, _ = LIMITS["ask"]
    for _ in range(limit):
        client.post("/ask", json={"question": "hi"})
    blocked = client.post("/ask", json={"question": "hi"})
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0


def test_ask_and_moc_have_separate_budgets(parts):
    client, _ = parts
    for _ in range(LIMITS["ask"][0]):
        client.post("/ask", json={"question": "hi"})
    # ask is now spent; moc must still be answerable (its upstream is unset, so
    # it fails differently - but not with 429)
    assert client.post("/ask", json={"question": "hi"}).status_code == 429
    assert client.post("/moc/assess",
                       json={"tag": "P-1", "summary": "x"}).status_code != 429


# -- upload validation --------------------------------------------------------
def upload(client, name, data=b"hello"):
    return client.post("/ingest", files={"file": (name, io.BytesIO(data),
                                                  "application/octet-stream")})


def test_a_disallowed_extension_is_refused_before_any_parser(parts):
    client, _ = parts
    r = upload(client, "malware.exe")
    assert r.status_code == 415


def test_an_oversized_file_is_refused(parts):
    client, _ = parts
    from gateway.routes.documents import MAX_UPLOAD_BYTES
    r = upload(client, "big.pdf", data=b"x" * (MAX_UPLOAD_BYTES + 1))
    assert r.status_code == 413


def test_an_empty_file_is_refused(parts):
    client, _ = parts
    r = upload(client, "empty.csv", data=b"")
    assert r.status_code == 400


def test_an_allowed_file_passes_the_gate(parts):
    client, _ = parts
    r = upload(client, "notes.md", data=b"# hello")
    assert r.status_code == 200
