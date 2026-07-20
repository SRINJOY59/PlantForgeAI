"""Permit-to-Work routes — proxied to the agents service.

Thin, like moc.py: the gateway forwards and relays.  The permit logic,
the graph tools, and the grounding check all live in the agents service.
A permit narrative that is wrong is a safety event; it must be generated
where the evidence is, not summarised through an extra hop.
"""

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse

from plantmind_core.schemas import PermitRequest

from gateway.deps import get_agents_http, require_role
from gateway.ratelimit import rate_limit

router = APIRouter()
# PTW requires engineer role and is rate-limited — every call is a billed,
# multi-tool LLM round-trip that also carries a safety obligation.
metered = [require_role("engineer"), Depends(rate_limit("permit"))]


@router.post("/permit/draft", dependencies=metered)
async def draft_permit(request: PermitRequest,
                       http: httpx.AsyncClient = Depends(get_agents_http)):
    """Draft a Permit-to-Work for the described job.

    Returns a structured WorkPermit: isolation checklist, hazard list, required
    PPE, governing clauses and procedures — all drawn from graph evidence, not
    generic templates.  The permit authority reviews and signs; this system
    never approves.
    """
    resp = await http.post("/permit/draft", json=request.model_dump())
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type="application/json")


@router.post("/permit/draft/stream", dependencies=metered)
async def draft_permit_stream(request: PermitRequest,
                              http: httpx.AsyncClient = Depends(get_agents_http)):
    """The same PTW draft, streamed as Server-Sent Events.

    Surfaces evidence-gathering steps live, then the narrative token-by-token,
    then the complete structured WorkPermit at the end as a 'done' event.
    """
    async def relay():
        async with http.stream("POST", "/permit/draft/stream",
                               json=request.model_dump()) as upstream:
            async for chunk in upstream.aiter_raw():
                yield chunk

    return StreamingResponse(relay(), media_type="text/event-stream")
