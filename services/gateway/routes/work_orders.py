"""Drafted work orders, and the planner's decision on them.

Engineer-gated at both ends. Reading a draft is reading what the plant intends
to do to itself; approving one commits money and a technician's shift. Neither
belongs to an operator account, and hiding the nav item is not a control.
"""

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from gateway.auth import current_user
from gateway.deps import get_service, require_role, sse

router = APIRouter()


class Decision(BaseModel):
    decision: Literal["approved", "rejected"]


class ScheduleRequest(BaseModel):
    """A proposed slot, as the engineer typed it.

    Only the slot and the note. The crew is NOT taken from the request: the
    Slack message names who is going in, and that is part of what an approver
    is agreeing to, so it is read off the roster here rather than asserted by
    the client. It is still only a snapshot - the dispatch re-reads the roster
    at approval time, so somebody added in between still gets the job.
    """
    window_start: str = ""
    window_end: str = ""
    notes: str = ""


class CrewMember(BaseModel):
    name: str
    email: str
    lang: str = "en"
    phone: str = ""


def _engineer_key(user: dict) -> str:
    """Whose roster this is. Off the verified token, never the request - the
    alternative is an engineer being able to dispatch work by naming somebody
    else's crew."""
    return (user.get("email") or user.get("sub", "")).strip().lower()


@router.get("/work-orders/drafts", dependencies=[require_role("engineer")])
async def drafts(after: str = "0", svc=Depends(get_service)):
    """Replays existing drafts, then follows live ones.

    Each is merged with its current decision AND schedule status on the way
    out. The stream entry itself is immutable, so a draft approved in an
    earlier session would otherwise replay as pending and invite a second
    approval of the same work.
    """
    async def events():
        cursor = after
        while True:
            entries = await svc.read_draft_work_orders_async(cursor, 15000)
            if not entries:
                yield ": keep-alive\n\n"
                continue
            decisions = svc.work_order_decisions()
            schedules = svc.work_order_schedules()
            for entry_id, payload in entries:
                cursor = entry_id
                record = decisions.get(entry_id) or {}
                sched = schedules.get(entry_id) or {}
                yield sse("work_order", {
                    "id": entry_id,
                    **json.loads(payload),
                    "status": record.get("decision", "pending_approval"),
                    "decided_by": record.get("by"),
                    "schedule_status": sched.get("status"),
                    "schedule": sched if sched else None,
                })
    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/work-orders/{draft_id}/decision",
             dependencies=[require_role("engineer")])
def decide(draft_id: str, body: Decision, svc=Depends(get_service),
           user: dict = Depends(current_user)):
    """Approve or reject a draft.

    The approver comes off the verified token, never the request body - same
    reason a correction's author does. Who signed off a piece of work is
    something we establish, not something the client asserts.
    """
    if not draft_id:
        raise HTTPException(400, "missing draft id")
    who = user.get("email") or user.get("sub", "unknown")
    svc.decide_work_order(draft_id, body.decision, who)
    return {"id": draft_id, "status": body.decision, "decided_by": who}


# ---------------------------------------------------------- scheduling
@router.post("/work-orders/{draft_id}/schedule",
             dependencies=[require_role("engineer")])
def schedule(draft_id: str, body: ScheduleRequest,
             svc=Depends(get_service),
             user: dict = Depends(current_user)):
    """Propose a time window and crew, and ask Slack to authorise it.

    The engineer's half of the flow ends here. Nothing reaches a worker on the
    strength of this call: the schedule is recorded as pending, the console
    shows it as awaiting approval, and only the Slack return path (routes/
    slack.py) can move it. Re-proposing after a rejection is allowed and is the
    point of keeping the schedule separate from the draft; re-proposing while
    one is still pending is not, because two live approval requests for the
    same work is how the same crew gets dispatched twice.
    """
    if not draft_id:
        raise HTTPException(400, "missing draft id")

    who = user.get("email") or user.get("sub", "unknown")

    # Read the draft back off the stream rather than taking it from the body:
    # the Slack message states what is being approved, and it must state what
    # the plant actually drafted, not what a client says it drafted.
    draft = svc.draft_by_id(draft_id)
    if draft is None:
        raise HTTPException(404, "draft not found")

    existing = svc.work_order_schedule(draft_id)
    if existing and existing.get("status") == "pending_approval":
        raise HTTPException(409, "this work order is already awaiting Slack "
                                 "approval")

    schedule_record = {
        "window_start": body.window_start,
        "window_end": body.window_end,
        "crew_names": [w.get("name") or w.get("email")
                       for w in svc.crew(_engineer_key(user))],
        "notes": body.notes,
        "requested_by": who,
    }

    result = svc.schedule_work_order(draft_id, schedule_record, draft)
    return {"id": draft_id, "schedule": result}


@router.get("/work-orders/{draft_id}/schedule",
            dependencies=[require_role("engineer")])
def get_schedule(draft_id: str, svc=Depends(get_service)):
    """Read the current schedule status for a draft."""
    sched = svc.work_order_schedule(draft_id)
    if sched is None:
        return {"id": draft_id, "schedule": None}
    return {"id": draft_id, "schedule": sched}


# -------------------------------------------------------------- crew roster
@router.get("/crew", dependencies=[require_role("engineer")])
def list_crew(svc=Depends(get_service),
              user: dict = Depends(current_user)):
    """The engineer's crew roster — workers who receive dispatched orders."""
    return {"crew": svc.crew(_engineer_key(user))}


@router.post("/crew", dependencies=[require_role("engineer")])
def add_crew(member: CrewMember, svc=Depends(get_service),
             user: dict = Depends(current_user)):
    """Add a worker to the engineer's crew roster, or update one.

    Keyed by email, so adding the same person twice corrects their language
    rather than creating a second row that would get the job card twice.
    """
    key = _engineer_key(user)
    email = member.email.strip().lower()
    if not email:
        raise HTTPException(400, "a crew member needs an email - it is how "
                                 "their job card finds them when they sign in")
    worker = {
        "id": email,
        "name": member.name.strip() or email,
        "email": email,
        "lang": (member.lang or "en").strip() or "en",
        "phone": member.phone.strip(),
    }
    svc.add_crew_member(key, worker)
    return {"status": "added", "worker": worker}


@router.delete("/crew/{worker_id}", dependencies=[require_role("engineer")])
def remove_crew(worker_id: str, svc=Depends(get_service),
                user: dict = Depends(current_user)):
    """Remove a worker from the engineer's crew roster.

    Job cards already dispatched to them are left alone. Taking somebody off a
    roster says nothing about work they were already sent and may already be
    doing, and silently emptying their phone mid-shift would be worse than
    leaving a stale card they can close.
    """
    removed = svc.remove_crew_member(_engineer_key(user), worker_id.lower())
    if not removed:
        raise HTTPException(404, "worker not found in roster")
    return {"status": "removed", "worker_id": worker_id}



@router.post("/work-orders/{draft_id}/dispatch",
             dependencies=[require_role("engineer")])
async def dispatch(draft_id: str, svc=Depends(get_service)):
    """Send an approved order to the crew again.

    The retry, not the trigger - approval already dispatches. This exists for
    the two cases where that was not enough: the dispatch failed after the
    approval was recorded, and a crew member was added afterwards. It refuses
    anything not approved, so it can never become a way around Slack.
    """
    try:
        recipients = await svc.redispatch(draft_id)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"id": draft_id, "dispatched_to": recipients}


@router.get("/work-orders/schedules", dependencies=[require_role("engineer")])
def schedules(svc=Depends(get_service)):
    """Every schedule and where its approval has got to.

    The drafts stream cannot carry this. A stream entry is immutable and its
    cursor only moves forward, so a console that has already replayed a draft
    will never see it again - and the approval it is waiting for happens in
    Slack, minutes later, with nothing new landing on the stream to carry the
    news back. One small polled read is what turns "awaiting approval" into
    "approved" on a card the engineer is already looking at.
    """
    return {"schedules": svc.work_order_schedules()}
