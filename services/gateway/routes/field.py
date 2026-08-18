"""Field Copilot — the worker persona's only backend surface.

A field worker stands at an asset and asks a question, by voice or text, in
their own language. These endpoints give them:

  GET  /field/assets            - what they can scope the copilot to
  GET  /field/asset/{tag}/context - the live analytic state of one asset
  POST /field/ask/stream        - an asset-scoped, multilingual grounded answer

The answer path deliberately REUSES retrieval's /ask/stream rather than owning
a second Q&A pipeline: it assembles the asset's live state and a language
directive into the alert_context the pipeline already understands, then relays
the same SSE stream the console's Ask page consumes. So a field answer is the
same grounded, cited answer an engineer gets - scoped to an asset, spoken back,
and in the worker's language.

Gated at require_role("worker"): worker is the lowest rank, so this admits the
field persona and every console role above it (an engineer can preview the
copilot), while the /app console stays closed to workers.
"""

import json

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from plantmind_core.schemas import Turn

from gateway.deps import get_http, get_service, require_role
from gateway.ratelimit import rate_limit

router = APIRouter()

MAX_HISTORY = 8

# Languages the copilot offers. The label is what the worker sees; the code is
# the BCP-47 tag the browser's speech engine and the model both understand. The
# model is natively multilingual, so this list is a UX choice, not a capability
# limit - it just has to agree with the frontend selector.
SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ar": "Arabic",
    "zh": "Chinese",
    "pt": "Portuguese",
}


class FieldAskRequest(BaseModel):
    question: str
    asset: str | None = None                 # the tag the worker scoped to
    lang: str = "en"                         # BCP-47 language code
    history: list[Turn] = Field(default_factory=list, max_length=MAX_HISTORY)


@router.get("/field/assets", dependencies=[require_role("worker")])
async def field_assets(svc=Depends(get_service)):
    """The asset universe a worker can scope the copilot to."""
    return {"assets": svc.list_assets()}


@router.get("/field/asset/{tag}/context", dependencies=[require_role("worker")])
async def field_asset_context(tag: str, svc=Depends(get_service)):
    """Live analytic state of one asset: standing alarms + last diagnosis.

    The numeric trend is intentionally not here - the field client tails the
    plant:telemetry WebSocket for that. This is the state a phone can't derive:
    which alarms stand, and what diagnostics last concluded.
    """
    return svc.asset_context(tag)


def _language_directive(lang: str) -> str:
    """Tell the model which language to answer in.

    Only language lives here now - the field-worker *tone* (short, concrete,
    safety-first) comes from persona="worker", set on the request below, so the
    two concerns stay separate: persona decides how it sounds, this decides
    which language it is in. Carried in alert_context because that is the free-
    text context slot the retrieval prompt already injects. Falls back to
    English on an unknown code rather than trusting an arbitrary client string.
    """
    name = SUPPORTED_LANGUAGES.get(lang, "English")
    return f"IMPORTANT: Answer entirely in {name}."


def _asset_state_block(svc, tag: str) -> str:
    """Render the asset's live state as compact text for the prompt context."""
    ctx = svc.asset_context(tag)
    lines = [f"Asset in question: {tag} (unit {ctx.get('unit')})."]
    alarms = ctx.get("active_alarms") or []
    if alarms:
        lines.append("Standing alarms:")
        for a in alarms:
            lines.append(
                f"  - {a.get('level')} ({a.get('severity')}): value="
                f"{a.get('value')} limit={a.get('limit')} "
                f"setpoint={a.get('setpoint')}")
    else:
        lines.append("No standing alarms on this asset.")
    diag = ctx.get("diagnosis")
    if diag and diag.get("candidates"):
        lines.append("Latest diagnosis candidate causes (most likely first):")
        for c in diag["candidates"]:
            score = c.get("score")
            score_s = f" (score {score:.2f})" if isinstance(score, (int, float)) else ""
            lines.append(f"  - {c.get('label')}{score_s}")
    return "\n".join(lines)


@router.post("/field/ask/stream", dependencies=[require_role("worker"),
                                                Depends(rate_limit("ask"))])
async def field_ask_stream(request: FieldAskRequest,
                           http: httpx.AsyncClient = Depends(get_http),
                           svc=Depends(get_service)):
    """Asset-scoped, multilingual grounded answer, streamed as SSE.

    Builds alert_context = language directive + live asset state, then relays
    retrieval's /ask/stream unchanged - the same pipeline, evidence, and SSE
    shape the console's Ask page uses.
    """
    parts = [_language_directive(request.lang)]
    if request.asset:
        try:
            parts.append(_asset_state_block(svc, request.asset))
        except Exception:
            pass                              # never fail the answer on context
    alert_context = "\n\n".join(parts)

    upstream_body = {
        "question": request.question,
        "history": [t.model_dump() for t in request.history],
        "alert_context": alert_context,
        "persona": "worker",              # drives the field-worker tone
    }

    async def relay():
        async with http.stream("POST", "/ask/stream", json=upstream_body) as up:
            async for chunk in up.aiter_raw():
                yield chunk

    return StreamingResponse(relay(), media_type="text/event-stream")


@router.get("/field/languages", dependencies=[require_role("worker")])
async def field_languages():
    """The languages the copilot offers, for the client's selector."""
    return JSONResponse({"languages": [{"code": c, "label": l}
                                       for c, l in SUPPORTED_LANGUAGES.items()]})
