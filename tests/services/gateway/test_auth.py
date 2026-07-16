"""The gateway is the security boundary: a token the frontend attaches means
nothing until this verifies it. These tests pin that a forged/expired/absent
token is rejected, and that the demo escape hatch is explicit."""

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from plantmind_core.config import get_settings

from gateway.deps import get_service
from gateway.main import app
from gateway.service import GatewayService
from conftest import FakeBus, FakeSender, FakeStore

SECRET = "test-jwt-secret"


def token(secret=SECRET, exp_offset=3600, aud="authenticated"):
    return jwt.encode(
        {"sub": "user-1", "email": "eng@plant.example", "aud": aud,
         "exp": int(time.time()) + exp_offset},
        secret, algorithm="HS256")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    get_settings.cache_clear()
    svc = GatewayService(FakeStore(), FakeBus(), FakeSender())
    app.dependency_overrides[get_service] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_valid_token_is_accepted(client):
    resp = client.get("/metrics",
                      headers={"Authorization": f"Bearer {token()}"})
    assert resp.status_code == 200


def test_no_token_is_rejected(client):
    assert client.get("/metrics").status_code == 401


def test_token_signed_with_wrong_secret_is_rejected(client):
    resp = client.get("/metrics",
                      headers={"Authorization": f"Bearer {token('attacker')}"})
    assert resp.status_code == 401


def test_expired_token_is_rejected(client):
    resp = client.get(
        "/metrics",
        headers={"Authorization": f"Bearer {token(exp_offset=-60)}"})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"]


def test_wrong_audience_is_rejected(client):
    resp = client.get(
        "/metrics",
        headers={"Authorization": f"Bearer {token(aud='someone-else')}"})
    assert resp.status_code == 401


def test_garbage_bearer_is_rejected(client):
    assert client.get("/metrics",
                      headers={"Authorization": "Bearer not-a-jwt"}
                      ).status_code == 401


def test_health_stays_open_for_container_healthchecks(client):
    assert client.get("/health").status_code == 200


def test_protected_routers_reject_anonymous(client):
    # the blanket router dependency, not per-endpoint memory
    assert client.get("/graph").status_code == 401
    assert client.post("/ask", json={"question": "hi"}).status_code == 401


def test_open_when_secret_unset(monkeypatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "")
    get_settings.cache_clear()
    svc = GatewayService(FakeStore(), FakeBus(), FakeSender())
    app.dependency_overrides[get_service] = lambda: svc
    try:
        # demo mode: no secret configured, gateway serves without a token
        assert TestClient(app).get("/metrics").status_code == 200
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
