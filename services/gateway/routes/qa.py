"""Q&A endpoints - proxied to the retrieval service. The gateway stays thin
here: it forwards the request and relays the SSE stream unchanged."""

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from plantmind_core.schemas import Turn

from gateway.deps import get_http

router = APIRouter()

# a thread only has to reach back far enough to resolve a reference, and the
# body is user-supplied - cap it here rather than trust the client
MAX_HISTORY = 8


class AskRequest(BaseModel):
    question: str
    history: list[Turn] = Field(default_factory=list, max_length=MAX_HISTORY)


@router.post("/ask")
async def ask(request: AskRequest, http: httpx.AsyncClient = Depends(get_http)):
    resp = await http.post("/ask", json=request.model_dump())
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type="application/json")


@router.post("/ask/stream")
async def ask_stream(request: AskRequest,
                     http: httpx.AsyncClient = Depends(get_http)):
    async def relay():
        async with http.stream("POST", "/ask/stream",
                               json=request.model_dump()) as upstream:
            async for chunk in upstream.aiter_raw():
                yield chunk
    return StreamingResponse(relay(), media_type="text/event-stream")
