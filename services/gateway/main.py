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
from gateway.routes import (compliance, documents, events, graph, moc, permit, qa,
                            reports, simulation, system, work_orders)
from gateway.security import SecurityHeadersMiddleware, cors_origins
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
# security headers first so CORS (added after) stays the outermost middleware and
# answers preflight before anything else runs
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(get_settings().cors_origins),
    # bearer tokens ride in the Authorization header, not cookies, so we never
    # need credentialed CORS - and not needing it lets us keep a real allowlist
    # instead of the "*"-with-credentials combination browsers forbid anyway
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"])

# auth is applied per-router rather than per-endpoint: a new endpoint is
# protected by default instead of by remembering to protect it
protected = [Depends(current_user)]
app.include_router(qa.router, dependencies=protected)
app.include_router(moc.router, dependencies=protected)
app.include_router(documents.router, dependencies=protected)
app.include_router(graph.router, dependencies=protected)
app.include_router(events.router, dependencies=protected)
app.include_router(permit.router, dependencies=protected)
app.include_router(work_orders.router, dependencies=protected)
app.include_router(reports.router, dependencies=protected)
app.include_router(compliance.router, dependencies=protected)
app.include_router(simulation.router)
app.include_router(system.router)   # /health must stay open for healthchecks
