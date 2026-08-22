"""Entry point for the knowledge-capture interview service. Run locally with:

    uvicorn interview.main:app --port 8002

Thin by design: the app wires the service and the live WebRTC connection state
onto app.state in the lifespan, and mounts the routes. Everything else lives in
its layer - api/ (HTTP), session/ (lifecycle), domain/ (the interview brain),
voice/ (audio), context/ (grounding), handover/ (output)."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from plantmind_core.config import get_settings

from interview.api import router
from interview.session import InterviewService

# The browser calls this service cross-origin: the SPA is served from the UI
# host and the interview API sits behind the gateway's host, so every request
# is preflighted. Hard-coding the vite dev origins meant a deployed UI got a
# CORS rejection on the very first /health call and reported the service as
# unreachable. Same CORS_ORIGINS the gateway reads, dev origins kept for
# `npm run dev` against a local service.
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _origins() -> list[str]:
    configured = [o.strip() for o in get_settings().cors_origins.split(",")
                  if o.strip()]
    return list(dict.fromkeys(configured + DEV_ORIGINS))


# Where this app is mounted, when it shares a hostname with another service.
# The GKE deployment puts it behind api.<host>/interview because a dedicated
# domain would mean re-provisioning the managed TLS cert; the L7 load balancer
# forwards the path unchanged, so the prefix has to be real routes.
#
# uvicorn --root-path does NOT do this job: it advertises the prefix for URL
# generation, and Starlette matches routes against the untouched path, so
# /interview/health still 404s. The router has to carry the prefix.
PATH_PREFIX = os.environ.get("INTERVIEW_PATH_PREFIX", "").rstrip("/")


@asynccontextmanager
async def lifespan(app):
    app.state.service = InterviewService.from_settings()
    app.state.conns = {}            # pc_id -> SmallWebRTCConnection
    app.state.active_voice = set()  # session ids with a live bot
    yield


app = FastAPI(title="plantmind-interview", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_methods=["*"], allow_headers=["*"])

app.include_router(router, prefix=PATH_PREFIX)
