"""FastAPI adapter for the knowledge-capture interview service. Run locally
with:

    uvicorn interview.main:app --port 8002

REST handles sessions and the finished README; /api/offer is the WebRTC
signaling leg of the Pipecat voice pipeline (imported lazily so the REST
API - and the text debug mode - work even without the voice dependencies
installed)."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from plantmind_core.telemetry import get_logger

from interview.auth import current_user
from interview.config import get_config
from interview.memory import SessionMemory
from interview.readme_gen import ingest_readme
from interview.service import InterviewService

log = get_logger("interview.main")

_service: InterviewService = None


@asynccontextmanager
async def lifespan(app):
    global _service
    _service = InterviewService.from_settings()
    app.state.conns = {}            # pc_id -> SmallWebRTCConnection
    app.state.active_voice = set()  # session ids with a live bot
    yield


app = FastAPI(title="plantmind-interview", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"])


class CreateSessionRequest(BaseModel):
    profile: dict


class TextRequest(BaseModel):
    text: str


def _get(session_id: str) -> SessionMemory:
    memory = _service.get(session_id)
    if memory is None:
        raise HTTPException(404, "unknown session")
    return memory


def _topic_view(memory: SessionMemory) -> list:
    return [{"id": t.id, "title": t.title, "category": t.category,
             "status": t.status, "coverage": round(t.coverage, 2),
             "facts_count": len(t.facts)} for t in memory.topics]


@app.post("/sessions")
async def create_session(req: CreateSessionRequest,
                         user=Depends(current_user)):
    memory = await _service.create_session(req.profile)
    return {"session_id": memory.session_id,
            "brief": memory.context.brief,
            "topics": _topic_view(memory)}


@app.get("/sessions/{session_id}")
def get_session(session_id: str, user=Depends(current_user)):
    memory = _get(session_id)
    return {"session_id": memory.session_id,
            "status": memory.status,
            "overall_coverage": round(memory.overall_coverage(), 2),
            "topics": _topic_view(memory),
            "transcript_tail": memory.transcript[-12:],
            "readme_ready": memory.readme_path is not None,
            "staging_key": memory.staging_key,
            "error": memory.error}


@app.post("/sessions/{session_id}/end")
async def end_session(session_id: str, user=Depends(current_user)):
    memory = _get(session_id)
    _service.request_end(memory)
    # with no live voice bot to say goodbye and finalize, do it directly
    if session_id not in app.state.active_voice \
            and memory.status == "ending":
        asyncio.create_task(_service.finalize(memory))
    return {"status": memory.status}


@app.get("/sessions/{session_id}/readme")
def get_readme(session_id: str, download: bool = False,
               user=Depends(current_user)):
    memory = _get(session_id)
    if not memory.readme_path:
        raise HTTPException(409, f"readme not ready (status={memory.status})")
    try:
        text = open(memory.readme_path, encoding="utf-8").read()
    except OSError:
        raise HTTPException(410, "readme file missing on disk")
    headers = {}
    if download:
        employee = memory.profile.get("employee_id") or memory.session_id
        headers["Content-Disposition"] = \
            f'attachment; filename="knowledge_handover_{employee}.md"'
    return PlainTextResponse(text, media_type="text/markdown",
                             headers=headers)


@app.post("/sessions/{session_id}/ingest")
def reingest(session_id: str, user=Depends(current_user)):
    """Manual retry when the pipeline was down at finalize time."""
    memory = _get(session_id)
    if not memory.readme_path:
        raise HTTPException(409, "readme not ready")
    text = open(memory.readme_path, encoding="utf-8").read()
    memory.staging_key = ingest_readme(memory, text)
    memory.save()
    if memory.staging_key is None:
        raise HTTPException(503, "ingestion pipeline unreachable")
    return {"staging_key": memory.staging_key}


@app.post("/api/offer")
async def offer(request: Request, session_id: str,
                background_tasks: BackgroundTasks):
    """SmallWebRTC signaling. Possession of a live session_id is the
    credential here - the browser transport cannot attach auth headers."""
    cfg = get_config()
    if not cfg.voice_ready:
        raise HTTPException(503, "voice disabled: DEEPGRAM_API_KEY not set. "
                                 "Text mode is still available.")
    memory = _get(session_id)
    if memory.status in ("generating", "done"):
        raise HTTPException(409, "interview already finished")
    try:
        from interview import bot
    except ImportError as e:
        raise HTTPException(503, "voice dependencies not installed - "
                                 f"pip install -r infra/docker/requirements/"
                                 f"interview.txt ({str(e)[:120]})")

    body = await request.json()
    answer, conn, is_new = await bot.negotiate(body, app.state.conns)
    if is_new:
        background_tasks.add_task(_run_voice, conn, memory)
    return answer


@app.patch("/api/offer")
async def offer_ice(request: Request):
    """Trickle ICE: the client SDK PATCHes candidates it gathers after the
    initial offer to this same endpoint. Without this route they 405 and
    are silently dropped, which can prevent the connection from completing
    on anything but the simplest same-machine network path."""
    from interview import bot
    body = await request.json()
    conn = app.state.conns.get(body.get("pc_id"))
    if conn is None:
        raise HTTPException(404, "unknown peer connection")
    await bot.add_trickled_candidates(conn, body.get("candidates", []))
    return {"ok": True}


async def _run_voice(conn, memory: SessionMemory):
    from interview import bot
    app.state.active_voice.add(memory.session_id)
    try:
        await bot.run_bot(conn, memory, get_config())
    except Exception as e:
        log.error("voice bot crashed", session=memory.session_id,
                  error=str(e)[:300])
    finally:
        app.state.active_voice.discard(memory.session_id)
        # whatever ended the call, the captured knowledge gets written up
        await _service.finalize(memory)


@app.post("/debug/text/{session_id}")
async def debug_text(session_id: str, req: TextRequest,
                     user=Depends(current_user)):
    """The whole interview brain over plain text - for development and for
    running without a Deepgram key. Enable with INTERVIEW_TEXT_MODE=1."""
    if not get_config().text_mode:
        raise HTTPException(403, "set INTERVIEW_TEXT_MODE=1 to use text mode")
    memory = _get(session_id)
    if memory.status in ("generating", "done"):
        raise HTTPException(409, "interview already finished")
    reply = await _service.text_turn(memory, req.text)
    return {"reply": reply, "status": memory.status,
            "overall_coverage": round(memory.overall_coverage(), 2)}


@app.get("/health")
def health():
    cfg = get_config()
    return {"status": "ok", "voice_ready": cfg.voice_ready,
            "text_mode": cfg.text_mode}
