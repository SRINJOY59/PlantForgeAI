"""The agent alert stream, fanned out to browsers over SSE."""

import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from gateway.deps import get_service, sse

router = APIRouter()


@router.get("/alerts")
async def alerts(after: str = "$", svc=Depends(get_service)):
    """'after' is the last-seen stream id; '$' means only alerts from now on.
    Each event echoes its id so a reconnecting client can resume."""
    async def events():
        cursor = after
        while True:
            # the bus read blocks; keep it off the event loop
            entries = await asyncio.to_thread(svc.read_alerts, cursor, 15000)
            if not entries:
                yield ": keep-alive\n\n"
                continue
            for entry_id, payload in entries:
                cursor = entry_id
                yield sse("alert", {"id": entry_id, **json.loads(payload)})
    return StreamingResponse(events(), media_type="text/event-stream")
