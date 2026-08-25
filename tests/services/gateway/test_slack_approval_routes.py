"""The Slack callback endpoints, exercised through the real app.

These two routes are the only unauthenticated write path in the gateway, and
what they write is permission to send people into a plant. So the tests here
are almost entirely about refusal: unsigned requests, tampered tokens, expired
links, and - the one that is easy to miss - a link PREVIEW being enough to
approve the work.

That last one is why the link flow is split across GET and POST. Slack fetches
URLs that appear in messages so it can unfurl them, so a GET that decided
anything would decide it the instant the approval request was posted, before a
human had read it.
"""

import json
import time

import fakeredis
import pytest
from fastapi.testclient import TestClient

from plantmind_core.bus import RedisBus
from plantmind_core.notify import sign_approval

from gateway import deps
from gateway.deps import get_service
from gateway.main import app
from gateway.service import GatewayService
from conftest import FakeSender, FakeStore

DRAFT = {"equipment": "P-101B", "priority": "high", "order_type": "PM01",
         "recommended_fix": "Clean the strainer, then replace the seal."}


class FakeAgents:
    async def post(self, path, json=None, timeout=None):
        langs = (json or {}).get("langs") or ["en"]
        return _Resp({"briefs": {lang: {"lang": lang, "title": "t",
                                        "summary": "s", "steps": ["do it"],
                                        "safety": [], "ppe": [],
                                        "references": []} for lang in langs}})


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def wired(monkeypatch):
    bus = RedisBus(fakeredis.FakeRedis(decode_responses=True))
    svc = GatewayService(FakeStore(), bus, FakeSender())
    monkeypatch.setattr(GatewayService, "_agents_http",
                        staticmethod(lambda: FakeAgents()))
    monkeypatch.setattr("plantmind_core.notify.SlackNotifier.from_settings",
                        staticmethod(lambda redis_client=None: _MutedSlack()))
    # deps.wire, not just dependency_overrides: the Slack routes call
    # get_service() directly rather than through Depends, because their caller
    # is Slack and there is no dependency chain to hang it off.
    deps.wire(svc, None, None)
    app.dependency_overrides[get_service] = lambda: svc
    # No `with`: entering the context runs the lifespan hook, which builds a
    # real GatewayService against redis and minio and hangs without them.
    yield TestClient(app), svc, bus
    app.dependency_overrides.clear()


class _MutedSlack:
    enabled = False

    def post_work_order_approval(self, *a, **k):
        return False

    def post_work_order_dispatched(self, *a, **k):
        return False


def scheduled(bus, svc, crew=True):
    """A draft with a crew, scheduled and waiting on Slack."""
    draft_id = bus.publish_draft_work_order(json.dumps(DRAFT))
    if crew:
        bus.set_crew_member("eng@plant", {"id": "ravi@plant",
                                          "email": "ravi@plant",
                                          "name": "Ravi", "lang": "hi"})
    svc.schedule_work_order(draft_id, {"requested_by": "eng@plant",
                                       "window_start": "2026-09-01T08:00"},
                            DRAFT)
    return draft_id


# ------------------------------------------------------------- link previews
def test_opening_the_link_does_not_approve_anything(wired):
    """The one that matters. Slack, Outlook and every preview bot in the chain
    fetch links in messages; if GET decided, the crew would be dispatched the
    moment the approval request was posted."""
    client, svc, bus = wired
    draft_id = scheduled(bus, svc)

    res = client.get("/slack/approve",
                     params={"token": sign_approval(draft_id, "approved")})

    assert res.status_code == 200
    assert bus.work_order_schedule(draft_id)["status"] == "pending_approval"
    assert bus.assignments_for("ravi@plant") == []
    # It has to be obvious to the human that nothing has happened yet.
    assert "Confirm" in res.text


def test_pressing_the_button_on_that_page_approves_and_dispatches(wired):
    client, svc, bus = wired
    draft_id = scheduled(bus, svc)

    res = client.post("/slack/approve",
                      data={"token": sign_approval(draft_id, "approved")})

    assert res.status_code == 200
    assert bus.work_order_schedule(draft_id)["status"] == "approved"
    assignment, = bus.assignments_for("ravi@plant")
    assert assignment["brief"]["lang"] == "hi"


def test_a_tampered_link_is_refused(wired):
    client, svc, bus = wired
    draft_id = scheduled(bus, svc)

    res = client.post("/slack/approve", data={"token": "not-a-token"})

    assert res.status_code == 403
    assert bus.work_order_schedule(draft_id)["status"] == "pending_approval"


def test_an_expired_link_is_refused(wired):
    client, svc, bus = wired
    draft_id = scheduled(bus, svc)

    res = client.post("/slack/approve",
                      data={"token": sign_approval(draft_id, "approved", ttl_s=-1)})

    assert res.status_code == 403
    assert bus.work_order_schedule(draft_id)["status"] == "pending_approval"


def test_the_confirmation_page_keeps_its_stylesheet(wired):
    """The gateway's default CSP is default-src 'none', which is right for a
    JSON API and would strip these pages bare."""
    client, svc, bus = wired
    draft_id = scheduled(bus, svc)

    res = client.get("/slack/approve",
                     params={"token": sign_approval(draft_id, "approved")})

    assert "style-src 'unsafe-inline'" in res.headers["content-security-policy"]


# ------------------------------------------------------------------ buttons
def test_an_unsigned_interaction_is_refused(wired):
    """The signing check is the only thing between this endpoint and anyone on
    the internet who knows the URL."""
    client, svc, bus = wired
    draft_id = scheduled(bus, svc)
    payload = {"actions": [{"action_id": "work_order_approve",
                            "value": draft_id}],
               "user": {"username": "mallory"}}

    res = client.post("/slack/interactions",
                      data={"payload": json.dumps(payload)})

    assert res.status_code == 403
    assert bus.work_order_schedule(draft_id)["status"] == "pending_approval"


def test_a_correctly_signed_interaction_approves_and_dispatches(wired, monkeypatch):
    import hashlib
    import hmac

    secret = "s3cret"
    monkeypatch.setattr("plantmind_core.notify.approvals.get_settings",
                        lambda: _Settings(secret))

    client, svc, bus = wired
    draft_id = scheduled(bus, svc)
    payload = {"actions": [{"action_id": "work_order_approve",
                            "value": draft_id}],
               "user": {"username": "asha"}}
    body = f"payload={json.dumps(payload)}"
    ts = str(int(time.time()))
    sig = "v0=" + hmac.new(secret.encode(),
                           f"v0:{ts}:{body}".encode(),
                           hashlib.sha256).hexdigest()

    res = client.post("/slack/interactions", content=body,
                      headers={"X-Slack-Request-Timestamp": ts,
                               "X-Slack-Signature": sig,
                               "Content-Type": "application/x-www-form-urlencoded"})

    assert res.status_code == 200
    record = bus.work_order_schedule(draft_id)
    assert record["status"] == "approved"
    assert record["decided_by"] == "asha"
    assert len(bus.assignments_for("ravi@plant")) == 1


def test_a_replayed_interaction_is_refused(wired, monkeypatch):
    """The timestamp is inside the signed base string precisely so an old
    capture cannot be kept fresh by editing it."""
    import hashlib
    import hmac

    secret = "s3cret"
    monkeypatch.setattr("plantmind_core.notify.approvals.get_settings",
                        lambda: _Settings(secret))

    client, svc, bus = wired
    draft_id = scheduled(bus, svc)
    body = f'payload={json.dumps({"actions": [{"action_id": "work_order_approve", "value": draft_id}]})}'
    stale = str(int(time.time()) - 3600)
    sig = "v0=" + hmac.new(secret.encode(), f"v0:{stale}:{body}".encode(),
                           hashlib.sha256).hexdigest()

    res = client.post("/slack/interactions", content=body,
                      headers={"X-Slack-Request-Timestamp": stale,
                               "X-Slack-Signature": sig,
                               "Content-Type": "application/x-www-form-urlencoded"})

    assert res.status_code == 403
    assert bus.work_order_schedule(draft_id)["status"] == "pending_approval"


class _Settings:
    """Only the fields the approval module reads."""

    def __init__(self, signing_secret):
        self.slack_signing_secret = signing_secret
        self.slack_approval_secret = "link-key"
        self.slack_approval_ttl_s = 86400
        self.public_gateway_url = "http://localhost:8000"
        self.supabase_jwt_secret = ""
        self.slack_webhook_url = ""
        self.redis_url = ""


# ---------------------------------------------------------- engineer's side
def test_scheduling_twice_while_one_is_pending_is_refused(wired):
    """Two live approval requests for the same work is how one crew gets
    dispatched twice."""
    client, svc, bus = wired
    draft_id = scheduled(bus, svc)

    res = client.post(f"/work-orders/{draft_id}/schedule",
                      json={"window_start": "2026-09-02T08:00"})

    assert res.status_code == 409


def test_scheduling_an_unknown_draft_is_a_404(wired):
    client, *_ = wired

    res = client.post("/work-orders/9999999-0/schedule",
                      json={"window_start": "2026-09-02T08:00"})

    assert res.status_code == 404


def test_schedules_endpoint_reports_what_the_console_is_waiting_on(wired):
    client, svc, bus = wired
    draft_id = scheduled(bus, svc)

    body = client.get("/work-orders/schedules").json()

    assert body["schedules"][draft_id]["status"] == "pending_approval"
