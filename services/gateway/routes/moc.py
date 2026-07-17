"""Management of Change - proxied to the agents service.

Thin, like qa.py: the gateway forwards and relays. The reasoning belongs to the
agents service, which is where the graph tools and the grounding check live.
"""

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from plantmind_core.schemas import ChangeProposal

from gateway.deps import get_agents_http

router = APIRouter()


@router.post("/moc/assess")
async def assess(proposal: ChangeProposal,
                 http: httpx.AsyncClient = Depends(get_agents_http)):
    resp = await http.post("/assess", json=proposal.model_dump())
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type="application/json")
