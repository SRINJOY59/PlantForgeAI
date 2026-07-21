"""The plant's statutory position, and turning a due obligation into work.

Thin, like moc.py and permit.py: the gateway forwards and relays. Reading the
compliance position is engineer-gated because it is a map of where the plant is
exposed; drafting work off it is gated for the same reason approving a work
order is.
"""

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from gateway.deps import get_agents_http, require_role

router = APIRouter()


class ScheduleRequest(BaseModel):
    item_id: str


@router.get("/compliance", dependencies=[require_role("engineer")])
async def compliance(http: httpx.AsyncClient = Depends(get_agents_http)):
    resp = await http.get("/compliance")
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type="application/json")


@router.post("/compliance/schedule", dependencies=[require_role("engineer")])
async def schedule(request: ScheduleRequest,
                   http: httpx.AsyncClient = Depends(get_agents_http)):
    """Draft a preventive work order for one obligation. The draft lands on the
    same stream as every other one, so it is approved in Work Orders by the
    same person under the same rules - compliance does not get a side door
    into the plant's maintenance schedule."""
    resp = await http.post("/compliance/schedule", json=request.model_dump())
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type="application/json")
