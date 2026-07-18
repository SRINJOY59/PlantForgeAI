"""The HTTP surface. REST handles session lifecycle and the finished skills
document; /api/offer is the WebRTC signaling leg of the voice pipeline, imported
lazily so the REST API - and the text debug mode - work even without the voice
dependencies installed.

The service and the live-connection state live on app.state (set in the
lifespan), reached here through the get_service dependency and request.app."""

import asyncio

from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException,
                     Request)
from fastapi.responses import PlainTextResponse

from plantmind_core.telemetry import get_logger

from interview.api.schemas import CreateSessionRequest, TextRequest
from interview.auth import current_user
from interview.config import get_config
from interview.domain import SessionMemory
from interview.handover import SkillsWriter
from interview.session import InterviewService

log = get_logger("interview.api")

router = APIRouter()


def get_service(request: Request) -> InterviewService:
    return request.app.state.service


def _get(svc: InterviewService, session_id: str) -> SessionMemory:
    memory = svc.get(session_id)
    if memory is None:
        raise HTTPException(404, "unknown session")
    return memory


def _topic_view(memory: SessionMemory) -> list:
    return [{"id": t.id, "title": t.title, "category": t.category,
             "status": t.status, "coverage": round(t.coverage, 2),
             "facts_count": len(t.facts)} for t in memory.topics]


@router.post("/sessions")
async def create_session(req: CreateSessionRequest,
                         svc: InterviewService = Depends(get_service),
                         user=Depends(current_user)):
    memory = await svc.create_session(req.profile)
    return {"session_id": memory.session_id,
            "brief": memory.context.brief,
            "topics": _topic_view(memory)}


@router.get("/sessions/{session_id}")
def get_session(session_id: str,
                svc: InterviewService = Depends(get_service),
                user=Depends(current_user)):
    memory = _get(svc, session_id)
    return {"session_id": memory.session_id,
            "status": memory.status,
            "overall_coverage": round(memory.overall_coverage(), 2),
            "topics": _topic_view(memory),
            "transcript_tail": memory.transcript[-12:],
            "skills_ready": memory.skills_path is not None,
            "staging_key": memory.staging_key,
            "error": memory.error}


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: str, request: Request,
                      svc: InterviewService = Depends(get_service),
                      user=Depends(current_user)):
    memory = _get(svc, session_id)
    svc.request_end(memory)
    # with no live voice bot to say goodbye and finalize, do it directly
    if session_id not in request.app.state.active_voice \
            and memory.status == "ending":
        asyncio.create_task(svc.finalize(memory))
    return {"status": memory.status}


@router.get("/sessions/{session_id}/skills")
def get_skills(session_id: str, download: bool = False,
               svc: InterviewService = Depends(get_service),
               user=Depends(current_user)):
    memory = _get(svc, session_id)
    if not memory.skills_path:
        raise HTTPException(
            409, f"skills document not ready (status={memory.status})")
    try:
        text = open(memory.skills_path, encoding="utf-8").read()
    except OSError:
        raise HTTPException(410, "skills document missing on disk")
    headers = {}
    if download:
        employee = memory.profile.get("employee_id") or memory.session_id
        headers["Content-Disposition"] = \
            f'attachment; filename="skills_{employee}.md"'
    return PlainTextResponse(text, media_type="text/markdown", headers=headers)


@router.post("/sessions/{session_id}/ingest")
def reingest(session_id: str,
             svc: InterviewService = Depends(get_service),
             user=Depends(current_user)):
    """Manual retry when the pipeline was down at finalize time."""
    memory = _get(svc, session_id)
    if not memory.skills_path:
        raise HTTPException(409, "skills document not ready")
    text = open(memory.skills_path, encoding="utf-8").read()
    memory.staging_key = SkillsWriter.publish(memory, text)
    memory.save()
    if memory.staging_key is None:
        raise HTTPException(503, "ingestion pipeline unreachable")
    return {"staging_key": memory.staging_key}


@router.post("/api/offer")
async def offer(request: Request, session_id: str,
                background_tasks: BackgroundTasks,
                svc: InterviewService = Depends(get_service)):
    """SmallWebRTC signaling. Possession of a live session_id is the
    credential here - the browser transport cannot attach auth headers."""
    cfg = get_config()
    if not cfg.voice_ready:
        raise HTTPException(503, "voice disabled: DEEPGRAM_API_KEY not set. "
                                 "Text mode is still available.")
    memory = _get(svc, session_id)
    if memory.status in ("generating", "done"):
        raise HTTPException(409, "interview already finished")
    try:
        from interview.voice.signaling import WebRTCSignaler
    except ImportError as e:
        raise HTTPException(503, "voice dependencies not installed - "
                                 f"pip install -r infra/docker/requirements/"
                                 f"interview.txt ({str(e)[:120]})")

    body = await request.json()
    signaler = WebRTCSignaler(request.app.state.conns)
    answer, conn, is_new = await signaler.negotiate(body)
    if is_new:
        background_tasks.add_task(_run_voice, request.app, conn, memory, svc)
    return answer


@router.patch("/api/offer")
async def offer_ice(request: Request):
    """Trickle ICE: the client SDK PATCHes candidates it gathers after the
    initial offer to this same endpoint. Without this route they 405 and are
    silently dropped, which can prevent the connection from completing on
    anything but the simplest same-machine network path."""
    from interview.voice.signaling import WebRTCSignaler
    body = await request.json()
    signaler = WebRTCSignaler(request.app.state.conns)
    conn = signaler.get(body.get("pc_id"))
    if conn is None:
        raise HTTPException(404, "unknown peer connection")
    await signaler.add_candidates(conn, body.get("candidates", []))
    return {"ok": True}


async def _run_voice(app, conn, memory: SessionMemory, svc: InterviewService):
    from interview.voice.bot import VoiceBot
    app.state.active_voice.add(memory.session_id)
    try:
        await VoiceBot(memory, get_config()).run(conn)
    except Exception as e:
        log.error("voice bot crashed", session=memory.session_id,
                  error=str(e)[:300])
    finally:
        app.state.active_voice.discard(memory.session_id)
        # whatever ended the call, the captured knowledge gets written up
        await svc.finalize(memory)


@router.post("/debug/text/{session_id}")
async def debug_text(session_id: str, req: TextRequest,
                     svc: InterviewService = Depends(get_service),
                     user=Depends(current_user)):
    """The whole interview brain over plain text - for development and for
    running without a Deepgram key. Enable with INTERVIEW_TEXT_MODE=1."""
    if not get_config().text_mode:
        raise HTTPException(403, "set INTERVIEW_TEXT_MODE=1 to use text mode")
    memory = _get(svc, session_id)
    if memory.status in ("generating", "done"):
        raise HTTPException(409, "interview already finished")
    reply = await svc.text_turn(memory, req.text)
    return {"reply": reply, "status": memory.status,
            "overall_coverage": round(memory.overall_coverage(), 2)}


@router.get("/health")
def health():
    cfg = get_config()
    return {"status": "ok", "voice_ready": cfg.voice_ready,
            "text_mode": cfg.text_mode}
