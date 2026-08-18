"""The fault-mode library, proxied from retrieval (which owns every graph read).

A thin passthrough, same pattern as graph.py. The Library page in the UI
fetches its whole dataset through this; the diagnostics service reads Neo4j
directly (it has no HTTP API, only a stream consumer).
"""

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from gateway.deps import get_http, require_role

router = APIRouter()


@router.get("/diagnostics/library", dependencies=[require_role("engineer")])
async def fault_library(http: httpx.AsyncClient = Depends(get_http)):
    resp = await http.get("/diagnostics/library")
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type="application/json")
