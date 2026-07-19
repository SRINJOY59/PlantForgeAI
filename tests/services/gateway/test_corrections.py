"""A correction carries more weight in the graph than the document it
contradicts, so the thing worth pinning at the edge is who gets to sign one."""

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from plantmind_core import corrections
from plantmind_core.config import get_settings
from plantmind_core.queues import Flow

from gateway.deps import get_service
from gateway.main import app
from gateway.service import GatewayService
from conftest import FakeBus, FakeSender, FakeStore

SECRET = "test-jwt-secret"
BODY = {"question": "How many seal failures has P-101A had?",
        "answer": "Three, all cavitation [doc:sop-1].",
        "correction": "Only two were cavitation.",
        "cited_docs": ["sop-1"]}


def token(email="eng@plant.com", role="engineer"):
    # Shaped like a hook-minted Supabase token: the custom_jwt_claims hook nests
    # app_role under app_metadata, which is where _role_from_claims reads it.
    # Corrections are engineer-gated, so an authorized author carries that role.
    return jwt.encode({"sub": "user-1", "email": email, "aud": "authenticated",
                       "app_metadata": {"app_role": role},
                       "exp": int(time.time()) + 3600},
                      SECRET, algorithm="HS256")


@pytest.fixture
def parts(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    get_settings.cache_clear()
    store, sender = FakeStore(), FakeSender()
    svc = GatewayService(store, FakeBus(), sender)
    app.dependency_overrides[get_service] = lambda: svc
    yield TestClient(app), store, sender
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def post(client, body=None, email="eng@plant.com", role="engineer"):
    return client.post("/corrections", json=body or BODY,
                       headers={"Authorization": f"Bearer {token(email, role)}"})


def test_a_correction_is_accepted_and_staged(parts):
    client, store, sender = parts
    resp = post(client)
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert len(store.staged) == 1


def test_it_enters_the_pipeline_by_the_ordinary_road(parts):
    # a correction is just a document: same classify note as any upload
    client, _, sender = parts
    post(client)
    route, _ = sender.sent[0]
    assert route == Flow.ingest


def test_the_staged_document_is_named_as_a_correction(parts):
    # the classifier routes on this suffix, so it is a contract not a label
    client, store, _ = parts
    post(client)
    key = next(iter(store.staged))
    assert key.endswith(corrections.SUFFIX)


def test_the_document_holds_the_question_answer_and_fix(parts):
    client, store, _ = parts
    post(client)
    written = corrections.parse(next(iter(store.staged.values())).decode())
    assert written.question == BODY["question"]
    assert written.answer == BODY["answer"]
    assert written.correction == BODY["correction"]
    assert written.cited_docs == ["sop-1"]


def test_the_author_comes_off_the_token(parts):
    client, store, _ = parts
    post(client, email="senior@plant.com")
    written = corrections.parse(next(iter(store.staged.values())).decode())
    assert written.author == "senior@plant.com"


def test_an_operator_may_not_file_a_correction(parts):
    # A correction outweighs the document it contradicts, so the gate is the
    # point: an authenticated operator is still refused, and nothing is staged.
    client, store, _ = parts
    resp = post(client, role="operator")
    assert resp.status_code == 403
    assert not store.staged


def test_the_author_cannot_be_set_from_the_request_body(parts):
    # a correction outranks the document it overturns, so the signature has to
    # be something we established, never something the client asserted
    client, store, _ = parts
    post(client, {**BODY, "author": "ceo@plant.com"}, email="junior@plant.com")
    written = corrections.parse(next(iter(store.staged.values())).decode())
    assert written.author == "junior@plant.com"


def test_an_anonymous_correction_is_rejected(parts):
    client, store, _ = parts
    assert client.post("/corrections", json=BODY).status_code == 401
    assert store.staged == {}


def test_an_empty_correction_is_rejected(parts):
    client, store, _ = parts
    assert post(client, {**BODY, "correction": ""}).status_code == 422
    assert store.staged == {}
