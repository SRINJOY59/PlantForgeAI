"""Gateway hardening: the headers and the CORS lock are easy to add and easy to
regress silently, so they get pinned."""

from fastapi.testclient import TestClient

from gateway.main import app

client = TestClient(app)


def test_security_headers_are_on_every_response():
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in r.headers["content-security-policy"]


def test_a_foreign_origin_is_not_granted_cors_access():
    # the default allowlist is the dev SPA; an attacker page's origin must not
    # come back blessed in the CORS response
    r = client.get("/health", headers={"Origin": "https://evil.example"})
    assert r.headers.get("access-control-allow-origin") != "https://evil.example"
    assert r.headers.get("access-control-allow-origin") != "*"


def test_the_configured_origin_is_allowed():
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
