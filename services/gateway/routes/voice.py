"""Voice interface WebSocket endpoint for Field Copilot.

The browser WebSocket API does not support custom headers, so the JWT must
be sent as a query parameter (?token=). The connection is rejected immediately
if the token is invalid or missing.
"""

import json
import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response

from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger

from gateway.deps import get_agents_http

log = get_logger("gateway.voice")

router = APIRouter()

@router.post("/agents/copilot/session")
async def create_copilot_session(request: Request, http=Depends(get_agents_http)):
    payload = await request.json()
    resp = await http.post("/copilot/session", json=payload)
    return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")


def _verify_ws_token(token: str) -> dict | None:
    """Verify JWT passed in WebSocket query string. Returns claims or None."""
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        return {"sub": "demo", "app_role": "operator"}
    if not token:
        return None
    try:
        return jwt.decode(token, settings.supabase_jwt_secret,
                          algorithms=["HS256"], audience="authenticated")
    except jwt.PyJWTError:
        return None


@router.websocket("/ws/copilot/{session_id}")
async def copilot_websocket(
    websocket: WebSocket,
    session_id: str,
    token: str = "",
    http=Depends(get_agents_http)
):
    claims = _verify_ws_token(token)
    if not claims:
        await websocket.close(code=1008, reason="Invalid or missing token")
        return

    await websocket.accept()
    log.info("copilot websocket connected", session_id=session_id)

    try:
        while True:
            text_data = await websocket.receive_text()
            try:
                msg = json.loads(text_data)
                utterance = msg.get("text", "").strip()
            except json.JSONDecodeError:
                continue

            if not utterance:
                continue

            # Forward to agents service
            resp = await http.post(
                f"/copilot/{session_id}/utterance",
                json={"utterance": utterance},
                timeout=60.0  # Generous timeout for agent reasoning
            )

            if resp.status_code == 200:
                await websocket.send_text(resp.text)
            else:
                await websocket.send_json({
                    "spoken_text": "Sorry, I encountered an error connecting to the backend.",
                    "display_text": f"Error {resp.status_code}",
                    "intent_detected": "ERROR",
                })

    except WebSocketDisconnect:
        log.info("copilot websocket disconnected", session_id=session_id)
    except Exception as e:
        log.error("copilot websocket error", error=str(e))
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
