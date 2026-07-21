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


@router.get("/work-orders/drafts", dependencies=[require_role("engineer")])
async def drafts(after: str = "0", svc=Depends(get_service)):
    """Replays existing drafts, then follows live ones.

    Each is merged with its current decision on the way out. The stream entry
    itself is immutable, so a draft approved in an earlier session would
    otherwise replay as pending and invite a second approval of the same work.
    """
    async def events():
        cursor = after
        while True:
            entries = await svc.read_draft_work_orders_async(cursor, 15000)
            if not entries:
                yield ": keep-alive\n\n"
                continue
            decisions = svc.work_order_decisions()
            for entry_id, payload in entries:
                cursor = entry_id
                record = decisions.get(entry_id) or {}
                yield sse("work_order", {
                    "id": entry_id,
                    **json.loads(payload),
                    "status": record.get("decision", "pending_approval"),
                    "decided_by": record.get("by"),
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
