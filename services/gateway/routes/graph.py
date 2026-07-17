"""The plant graph, proxied from retrieval (which owns every graph read)."""

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from gateway.deps import get_http

router = APIRouter()


@router.get("/graph")
async def graph(limit: int = 400, http: httpx.AsyncClient = Depends(get_http)):
    resp = await http.get("/graph", params={"limit": limit})
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type="application/json")
