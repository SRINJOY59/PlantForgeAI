"""The gateway: the single public entry point. Composes the internal
services - proxies Q&A to retrieval, accepts uploads, serves citation
sources, fans out the alert stream - and owns edge concerns (CORS, and
later auth/rate-limit). The endpoints live in routes/; this file wires them.

    uvicorn gateway.main:app --port 8000
"""

from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from plantmind_core.config import get_settings
from gateway import deps
from gateway.auth import current_user
from gateway.routes import documents, events, graph, moc, qa, system
from gateway.service import GatewayService


@asynccontextmanager
async def lifespan(app):
    s = get_settings()
    http = httpx.AsyncClient(base_url=s.retrieval_url, timeout=120)
    # an assessment walks the graph over several tool calls, so it is slower
    # than a question by design rather than by accident
    agents_http = httpx.AsyncClient(base_url=s.agents_url, timeout=300)
    deps.wire(GatewayService.from_settings(), http, agents_http)
    yield
    await http.aclose()
    await agents_http.aclose()


app = FastAPI(title="plantmind-gateway", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

# auth is applied per-router rather than per-endpoint: a new endpoint is
# protected by default instead of by remembering to protect it
protected = [Depends(current_user)]
app.include_router(qa.router, dependencies=protected)
app.include_router(moc.router, dependencies=protected)
app.include_router(documents.router, dependencies=protected)
app.include_router(graph.router, dependencies=protected)
app.include_router(events.router, dependencies=protected)
app.include_router(system.router)   # /health must stay open for healthchecks
