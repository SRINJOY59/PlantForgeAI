import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from gateway.deps import get_service, sse

router = APIRouter()


@router.get("/work-orders/drafts")
async def drafts(after: str = "$", svc=Depends(get_service)):
    async def events():
        cursor = after
        while True:
            entries = await svc.read_draft_work_orders_async(cursor, 15000)
            if not entries:
                yield ": keep-alive\n\n"
                continue
            for entry_id, payload in entries:
                cursor = entry_id
                yield sse("work_order", {"id": entry_id, **json.loads(payload)})
    return StreamingResponse(events(), media_type="text/event-stream")
