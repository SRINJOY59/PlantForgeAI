"""Entry point for the knowledge-capture interview service. Run locally with:

    uvicorn interview.main:app --port 8002

Thin by design: the app wires the service and the live WebRTC connection state
onto app.state in the lifespan, and mounts the routes. Everything else lives in
its layer - api/ (HTTP), session/ (lifecycle), domain/ (the interview brain),
voice/ (audio), context/ (grounding), handover/ (output)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from interview.api import router
from interview.session import InterviewService


@asynccontextmanager
async def lifespan(app):
    app.state.service = InterviewService.from_settings()
    app.state.conns = {}            # pc_id -> SmallWebRTCConnection
    app.state.active_voice = set()  # session ids with a live bot
    yield


app = FastAPI(title="plantmind-interview", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"])

app.include_router(router)
