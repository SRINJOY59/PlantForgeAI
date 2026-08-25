"""The schedule -> Slack approval -> translated dispatch loop.

The tests worth having here are the ones about authority and delivery, because
those are what the feature is: work must not reach a crew without an approval,
an approval must not be replayable, and once it happens every worker must get
the job card in their own language.

The LLM is never called. The agents service is stubbed, which is exactly the
seam the gateway has in production - it does not own a model and must not grow
one - so stubbing it tests the real boundary rather than papering over it.
"""

import base64
import json

import fakeredis
import pytest

from plantmind_core.bus import RedisBus
from plantmind_core.notify import sign_approval, verify_approval
from plantmind_core.notify.approvals import ApprovalTokenError

from gateway.dispatch import crew_languages, dispatch_to_crew
from gateway.service import GatewayService
from conftest import FakeSender, FakeStore


DRAFT = {
    "equipment": "P-101B",
    "failure_mode": "seal leak",
    "order_type": "PM01",
    "priority": "high",
    "procedures": ["SOP-114"],
    "governing_clauses": ["IS 2062 cl.7"],
    "root_cause": "Suction strainer fouling drives cavitation.",
    "recommended_fix": "Clean the strainer, then replace the seal.",
}


class FakeAgents:
    """Stands in for the agents service's /work-order/brief."""

    def __init__(self, briefs=None, fail=False):
        self.calls = []
        self.fail = fail
        self._briefs = briefs

    async def post(self, path, json=None, timeout=None):
        self.calls.append((path, json))
        if self.fail:
            raise RuntimeError("agents unreachable")
        langs = json.get("langs") or ["en"]
        briefs = self._briefs or {
            lang: {"lang": lang, "title": f"title-{lang}",
                   "summary": f"summary-{lang}", "steps": [f"step-{lang}"],
                   "safety": [], "ppe": [], "references": ["SOP-114"]}
            for lang in langs
        }
        return FakeResponse({"briefs": briefs, "untranslatable": []})


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def bus():
    return RedisBus(fakeredis.FakeRedis(decode_responses=True))


@pytest.fixture
def svc(bus, monkeypatch):
    service = GatewayService(FakeStore(), bus, FakeSender())
    # Slack is off in tests; the notifier no-ops rather than reaching the net.
    monkeypatch.setattr("plantmind_core.notify.SlackNotifier.from_settings",
                        staticmethod(lambda redis_client=None: _MutedSlack()))
    return service


class _MutedSlack:
    enabled = False

    def post_work_order_approval(self, *a, **k):
        return False

    def post_work_order_dispatched(self, *a, **k):
        return False


def publish(bus, draft=DRAFT):
    return bus.publish_draft_work_order(json.dumps(draft))


# ------------------------------------------------------------------ reading
def test_draft_is_readable_back_by_its_stream_id(svc, bus):
    """The whole flow hangs off this: the Slack message, the brief and the
    dispatch all start by reading the draft back out of the stream."""
    draft_id = publish(bus)

    assert svc.draft_by_id(draft_id)["equipment"] == "P-101B"
    assert svc.draft_by_id("9999999-0") is None
    assert svc.draft_by_id("") is None


# --------------------------------------------------------------- authority
@pytest.mark.asyncio
async def test_nothing_dispatches_without_an_approval(svc, bus):
    draft_id = publish(bus)
    bus.set_crew_member("eng@plant", {"id": "w@plant", "email": "w@plant",
                                      "name": "Ravi", "lang": "hi"})
    svc.schedule_work_order(draft_id, {"requested_by": "eng@plant",
                                       "window_start": "2026-09-01T08:00"}, DRAFT)

    assert bus.work_order_schedule(draft_id)["status"] == "pending_approval"
    assert bus.assignments_for("w@plant") == []


@pytest.mark.asyncio
async def test_approval_dispatches_to_every_crew_member(svc, bus, monkeypatch):
    agents = FakeAgents()
    monkeypatch.setattr(GatewayService, "_agents_http", staticmethod(lambda: agents))

    draft_id = publish(bus)
    bus.set_crew_member("eng@plant", {"id": "ravi@plant", "email": "ravi@plant",
                                      "name": "Ravi", "lang": "hi"})
    bus.set_crew_member("eng@plant", {"id": "asha@plant", "email": "asha@plant",
                                      "name": "Asha", "lang": "ta"})
    svc.schedule_work_order(draft_id, {"requested_by": "eng@plant"}, DRAFT)

    record = await svc.handle_schedule_decision(draft_id, "approved",
                                                "planner", "button")

    assert record["status"] == "approved"
    assert len(record["dispatched_to"]) == 2

    ravi, = bus.assignments_for("ravi@plant")
    asha, = bus.assignments_for("asha@plant")
    assert ravi["brief"]["lang"] == "hi"
    assert asha["brief"]["lang"] == "ta"
    # The English source travels with both, for when a translation reads oddly.
    assert ravi["brief_en"]["lang"] == "en"
    assert ravi["status"] == "assigned"


@pytest.mark.asyncio
async def test_a_second_approval_changes_nothing(svc, bus, monkeypatch):
    """The Slack message carries a button AND a link, so the same human can
    plausibly answer twice. The second answer must not re-stamp the approver
    or, worse, flip an approval after a crew has been sent."""
    agents = FakeAgents()
    monkeypatch.setattr(GatewayService, "_agents_http", staticmethod(lambda: agents))

    draft_id = publish(bus)
    bus.set_crew_member("eng@plant", {"id": "ravi@plant", "email": "ravi@plant",
                                      "name": "Ravi", "lang": "hi"})
    svc.schedule_work_order(draft_id, {"requested_by": "eng@plant"}, DRAFT)

    first = await svc.handle_schedule_decision(draft_id, "approved", "asha", "button")
    second = await svc.handle_schedule_decision(draft_id, "rejected", "mallory", "link")

    assert first["decided_by"] == "asha"
    assert second is None
    assert bus.work_order_schedule(draft_id)["status"] == "approved"
    assert bus.work_order_schedule(draft_id)["decided_by"] == "asha"


@pytest.mark.asyncio
async def test_rejection_notifies_nobody(svc, bus, monkeypatch):
    agents = FakeAgents()
    monkeypatch.setattr(GatewayService, "_agents_http", staticmethod(lambda: agents))

    draft_id = publish(bus)
    bus.set_crew_member("eng@plant", {"id": "ravi@plant", "email": "ravi@plant",
                                      "name": "Ravi", "lang": "hi"})
    svc.schedule_work_order(draft_id, {"requested_by": "eng@plant"}, DRAFT)

    record = await svc.handle_schedule_decision(draft_id, "rejected", "planner", "link")

    assert record["status"] == "rejected"
    assert bus.assignments_for("ravi@plant") == []
    assert agents.calls == []


@pytest.mark.asyncio
async def test_decision_on_an_unscheduled_draft_is_refused(svc, bus):
    draft_id = publish(bus)
    assert await svc.handle_schedule_decision(draft_id, "approved", "x", "link") is None


# ---------------------------------------------------------------- delivery
def test_only_languages_the_crew_reads_are_requested():
    crew = [{"lang": "hi"}, {"lang": "hi"}, {"lang": "ta"}, {}]
    # English always, because it is the source and the fallback - but Hindi
    # once, not twice, for two Hindi-reading fitters on the same order.
    assert crew_languages(crew) == ["en", "hi", "ta"]


@pytest.mark.asyncio
async def test_a_translated_brief_is_reused_across_workers(bus):
    agents = FakeAgents()
    draft_id = publish(bus)
    for name, email in (("Ravi", "ravi@plant"), ("Sunil", "sunil@plant")):
        bus.set_crew_member("eng@plant", {"id": email, "email": email,
                                          "name": name, "lang": "hi"})
    schedule = {"draft_id": draft_id, "requested_by": "eng@plant"}

    await dispatch_to_crew(bus, DRAFT, schedule, agents)
    await dispatch_to_crew(bus, DRAFT, schedule, agents)

    # One upstream call for both workers, and none at all the second time:
    # the draft is immutable, so its brief can never go stale.
    assert len(agents.calls) == 1
    assert sorted(agents.calls[0][1]["langs"]) == ["en", "hi"]


@pytest.mark.asyncio
async def test_redispatch_does_not_reset_work_already_underway(bus):
    agents = FakeAgents()
    draft_id = publish(bus)
    bus.set_crew_member("eng@plant", {"id": "ravi@plant", "email": "ravi@plant",
                                      "name": "Ravi", "lang": "hi"})
    schedule = {"draft_id": draft_id, "requested_by": "eng@plant"}

    await dispatch_to_crew(bus, DRAFT, schedule, agents)
    assignment, = bus.assignments_for("ravi@plant")
    bus.update_assignment("ravi@plant", assignment["id"],
                          {"status": "in_progress"})

    await dispatch_to_crew(bus, DRAFT, schedule, agents)

    again, = bus.assignments_for("ravi@plant")
    assert again["status"] == "in_progress"


@pytest.mark.asyncio
async def test_dispatch_without_a_crew_is_reported_not_silent(svc, bus, monkeypatch):
    """An approved order nobody was told about is the worst outcome here, so
    it has to surface on the card rather than in a log line."""
    monkeypatch.setattr(GatewayService, "_agents_http",
                        staticmethod(lambda: FakeAgents()))
    draft_id = publish(bus)
    svc.schedule_work_order(draft_id, {"requested_by": "eng@plant"}, DRAFT)

    record = await svc.handle_schedule_decision(draft_id, "approved", "p", "button")

    assert record["status"] == "approved"      # the human's decision stands
    assert "no crew" in record["dispatch_error"]


@pytest.mark.asyncio
async def test_a_failed_dispatch_can_be_retried_without_re_approval(svc, bus, monkeypatch):
    monkeypatch.setattr(GatewayService, "_agents_http",
                        staticmethod(lambda: FakeAgents(fail=True)))
    draft_id = publish(bus)
    bus.set_crew_member("eng@plant", {"id": "ravi@plant", "email": "ravi@plant",
                                      "name": "Ravi", "lang": "hi"})
    svc.schedule_work_order(draft_id, {"requested_by": "eng@plant"}, DRAFT)
    record = await svc.handle_schedule_decision(draft_id, "approved", "p", "button")
    assert record["dispatch_error"]

    monkeypatch.setattr(GatewayService, "_agents_http",
                        staticmethod(lambda: FakeAgents()))
    recipients = await svc.redispatch(draft_id)

    assert len(recipients) == 1
    assert "dispatch_error" not in bus.work_order_schedule(draft_id)


@pytest.mark.asyncio
async def test_redispatch_refuses_an_unapproved_order(svc, bus):
    draft_id = publish(bus)
    svc.schedule_work_order(draft_id, {"requested_by": "eng@plant"}, DRAFT)

    with pytest.raises(ValueError):
        await svc.redispatch(draft_id)


# ------------------------------------------------------------ worker replies
def test_worker_progress_timestamps_are_written_once(svc, bus):
    bus.add_assignment("ravi@plant", {"id": "a1", "status": "assigned"})

    svc.update_assignment("ravi@plant", "a1", "done", "seal replaced")
    first = bus.assignment("ravi@plant", "a1")["completed_at"]
    svc.update_assignment("ravi@plant", "a1", "done")
    again = bus.assignment("ravi@plant", "a1")

    assert again["completed_at"] == first
    assert again["worker_note"] == "seal replaced"


def test_worker_cannot_update_an_assignment_that_is_not_theirs(svc, bus):
    bus.add_assignment("ravi@plant", {"id": "a1", "status": "assigned"})

    assert svc.update_assignment("mallory@plant", "a1", "done") is None


# ------------------------------------------------------------------ tokens
def test_an_approval_token_is_bound_to_one_draft_and_one_decision():
    token = sign_approval("1700-0", "approved")
    assert verify_approval(token) == ("1700-0", "approved")


def test_a_rejection_token_cannot_be_edited_into_an_approval():
    """The decision is inside the signed payload, not a query parameter beside
    it - otherwise the reject link is an approve link with one word changed.

    Forged the way an attacker actually would: rewrite the payload and keep the
    signature, which is the only part they cannot recompute."""
    token = sign_approval("1700-0", "rejected")
    payload, _, signature = token.partition(".")
    decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    tampered = decoded.replace(b"rejected", b"approved")
    forged = (base64.urlsafe_b64encode(tampered).decode().rstrip("=")
              + "." + signature)

    assert b"approved" in tampered              # the forgery is real
    with pytest.raises(ApprovalTokenError):
        verify_approval(forged)


def test_an_expired_link_is_refused():
    with pytest.raises(ApprovalTokenError):
        verify_approval(sign_approval("1700-0", "approved", ttl_s=-1))
