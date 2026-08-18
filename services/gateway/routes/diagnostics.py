"""The fault-mode library, proxied from retrieval (which owns every graph read).

A thin passthrough, same pattern as graph.py. The Library page in the UI
fetches its whole dataset through this; the diagnostics service reads Neo4j
directly (it has no HTTP API, only a stream consumer).
"""

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from gateway.deps import get_http, get_service, require_role

router = APIRouter()


@router.get("/diagnostics/library", dependencies=[require_role("engineer")])
async def fault_library(http: httpx.AsyncClient = Depends(get_http)):
    resp = await http.get("/diagnostics/library")
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type="application/json")


@router.post("/diagnostics/{diag_id}/investigate",
             dependencies=[require_role("engineer")])
async def investigate_diagnosis(diag_id: str, svc=Depends(get_service)):
    """Ask for an LLM root-cause analysis of one live diagnosis.

    Deliberately fire-and-forget: the request goes on a stream that the agents
    runtime consumes, runs the investigation grounded in this diagnosis, and
    publishes the result to the alert stream (type 'investigation', carrying
    diagnosis_id) which the client already tails. So this returns immediately
    with 'queued' rather than blocking a request on a multi-step LLM call."""
    svc._bus.request_rca(diag_id)
    return {"status": "queued", "diagnosis_id": diag_id}
