"""The agent alert stream, fanned out to browsers over SSE."""

import json
import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, Response

from gateway.deps import get_service, sse, get_agents_http

router = APIRouter()


@router.get("/alerts")
async def alerts(after: str = "$", svc=Depends(get_service)):
    """'after' is the last-seen stream id; '$' means only alerts from now on.
    Each event echoes its id so a reconnecting client can resume."""
    async def events():
        cursor = after
        while True:
            # awaited on the loop via the async redis client, NOT to_thread: a
            # connection spends its whole life parked on this read, and a
            # thread-per-open-tab hold is how a few dozen Alerts pages starved
            # the pool that Ask's graph reads run on. A parked await is free;
            # a parked thread is 1/32nd of the platform.
            entries = await svc.read_alerts_async(cursor, 15000)
            if not entries:
                yield ": keep-alive\n\n"
                continue
            for entry_id, payload in entries:
                cursor = entry_id
                yield sse("alert", {"id": entry_id, **json.loads(payload)})
    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/initial-alerts")
async def initial_alerts(http: httpx.AsyncClient = Depends(get_agents_http)):
    """Return real equipment failure patterns discovered from the knowledge graph."""
    resp = await http.get("/failures")
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type="application/json")
