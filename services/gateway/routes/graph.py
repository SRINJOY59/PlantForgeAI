"""The plant graph, proxied from retrieval (which owns every graph read)."""

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from gateway.deps import get_http, require_role

router = APIRouter()


@router.get("/graph", dependencies=[require_role("engineer")])
async def graph(limit: int = 400, http: httpx.AsyncClient = Depends(get_http)):
    resp = await http.get("/graph", params={"limit": limit})
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type="application/json")


@router.post("/graphql", dependencies=[require_role("engineer")])
async def graphql_proxy(request: Request,
                        http: httpx.AsyncClient = Depends(get_http)):
    """Forward GraphQL queries to retrieval's Strawberry endpoint."""
    body = await request.body()
    resp = await http.post("/graphql", content=body,
                           headers={"content-type": "application/json"})
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type="application/json")


@router.get("/graphql", dependencies=[require_role("engineer")])
async def graphql_playground(http: httpx.AsyncClient = Depends(get_http)):
    """Forward the GraphiQL IDE. Only POST was proxied, so the interactive
    explorer 404'd through the gateway even though the query path worked."""
    resp = await http.get("/graphql", headers={"accept": "text/html"})
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type=resp.headers.get("content-type", "text/html"))
