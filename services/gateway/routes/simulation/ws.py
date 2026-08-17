"""WebSocket bridge for streaming telemetry and alerts to the UI.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from gateway.deps import get_service
from plantmind_core import keys
from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger

log = get_logger("gateway.routes.simulation.ws")

router = APIRouter()


def verify_ws_token(token: str | None) -> dict:
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        return {"sub": "demo", "email": "demo@local", "app_role": "engineer", "demo": True}
    if not token:
        raise ValueError("Missing token")
    try:
        claims = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
    except Exception as e:
        raise ValueError(f"Invalid token: {e}")

    app_meta = claims.get("app_metadata") or {}
    role = app_meta.get("app_role") or claims.get("app_role") or "operator"
    claims["app_role"] = role if role in ["operator", "planner", "engineer", "admin"] else "operator"
    return claims


@router.websocket("/ws/plant-telemetry")
async def ws_telemetry(websocket: WebSocket, token: Optional[str] = None, unit: Optional[str] = None, svc=Depends(get_service)):
    await websocket.accept()
    log.info("WebSocket connection accepted")

    try:
        verify_ws_token(token)
    except ValueError as val_err:
        log.warning("WebSocket authentication failed", error=str(val_err))
        await websocket.close(code=1008, reason="Authentication failed")
        return

    telemetry_cursor = "$"
    alert_cursor = "$"

    r_async = svc._bus._async()

    async def send_telemetry():
        nonlocal telemetry_cursor
        while True:
            try:
                reply = await r_async.xread({"plant:telemetry": telemetry_cursor}, block=5000, count=100)
                if reply:
                    for _stream, entries in reply:
                        for entry_id, fields in entries:
                            telemetry_cursor = entry_id

                            tag_id = fields.get("tag_id", "")

                            if unit:
                                if unit == "CSTR" and not tag_id.startswith("CSTR"):
                                    continue
                                if unit == "COLUMN" and not tag_id.startswith("COLUMN"):
                                    continue

                            msg = {
                                "type": "telemetry",
                                "tag_id": tag_id,
                                "timestamp": fields.get("timestamp", ""),
                                "value": float(fields.get("value", "0")),
                                "unit": fields.get("unit", ""),
                                "status": fields.get("status", "GOOD")
                            }
                            await websocket.send_text(json.dumps(msg))
            except Exception as e:
                log.warning("WebSocket telemetry error", error=str(e))
                break
            await asyncio.sleep(0.1)

    async def send_alerts():
        nonlocal alert_cursor
        while True:
            try:
                reply = await r_async.xread({keys.ALERT_STREAM: alert_cursor}, block=5000, count=10)
                if reply:
                    for _stream, entries in reply:
                        for entry_id, fields in entries:
                            alert_cursor = entry_id
                            payload = json.loads(fields.get("payload", "{}"))

                            msg = {
                                "type": "alert",
                                "id": entry_id,
                                **payload
                            }
                            await websocket.send_text(json.dumps(msg))
            except Exception as e:
                log.warning("WebSocket alerts error", error=str(e))
                break
            await asyncio.sleep(0.5)

    t1 = asyncio.create_task(send_telemetry())
    t2 = asyncio.create_task(send_alerts())

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log.info("WebSocket client disconnected")
    finally:
        t1.cancel()
        t2.cancel()
        try:
            await asyncio.gather(t1, t2, return_exceptions=True)
        except Exception:
            pass
