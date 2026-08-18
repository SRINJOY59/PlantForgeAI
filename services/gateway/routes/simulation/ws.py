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

# how much of the alert stream a newly connected client is caught up on.
# generous because one alarm costs two entries here — the alarm and the
# investigation that answers it — and the Historian needs both to draw a lane.
ALERT_REPLAY_COUNT = 100

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

    crit_alert_cursor = "$"
    legacy_alert_cursor = "$"

    async def replay_recent_alerts():
        """Send the tail of the alert stream before following it live.

        The Alerts and Historian panels are built from what arrives on this
        socket, so a socket that only carries alerts raised after it connected
        shows an empty timeline on every page load and every reconnect — the
        alarms and the investigations that answered them are still on the
        stream, the browser just never hears about them.

        The cursor is handed back rather than left at "$": resuming from the
        newest replayed id is what makes this exactly-once. Starting the tail
        at "$" instead would drop anything published between this read and the
        first xread, and replaying from "0" would resend the whole stream.
        """
        try:
            recent = await r_async.xrevrange("alerts:critical", "+", "-",
                                             count=ALERT_REPLAY_COUNT)
        except Exception as e:
            log.warning("Failed to replay recent alerts", error=str(e))
            return "$"

        if not recent:
            # empty stream: "0" is safe and closes the gap that "$" would open
            return "0"

        for entry_id, fields in reversed(recent):
            try:
                raw_payload = fields.get("payload", "{}")
                payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
                await websocket.send_text(json.dumps({
                    "type": "alert", "id": entry_id, "replay": True, **payload,
                }))
            except Exception as e:
                log.warning("Failed to replay alert", entry_id=entry_id, error=str(e))
        return recent[0][0]

    async def send_alerts():
        nonlocal crit_alert_cursor, legacy_alert_cursor
        crit_alert_cursor = await replay_recent_alerts()
        while True:
            try:
                reply = await r_async.xread(
                    {"alerts:critical": crit_alert_cursor, "alerts": legacy_alert_cursor},
                    block=5000,
                    count=10
                )
                if reply:
                    for stream_name, entries in reply:
                        for entry_id, fields in entries:
                            if stream_name == "alerts:critical":
                                crit_alert_cursor = entry_id
                            else:
                                legacy_alert_cursor = entry_id

                            raw_payload = fields.get("payload", "{}")
                            payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload

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
