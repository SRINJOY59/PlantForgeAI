"""FastAPI adapter for the retrieval service - the service-level Q&A API
that the gateway and the eval runner call. Run locally with:

    uvicorn retrieval.main:app --port 8001
"""

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from retrieval.service import RetrievalService

_service = None


@asynccontextmanager
async def lifespan(app):
    global _service
    _service = RetrievalService.from_settings()
    yield


app = FastAPI(title="plantmind-retrieval", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/ask")
async def ask(request: AskRequest):
    answer = await _service.ask(request.question)
    return answer.model_dump(mode="json")


@app.post("/ask/stream")
async def ask_stream(request: AskRequest):
    async def events():
        async for kind, payload in _service.ask_stream(request.question):
            if kind == "token":
                yield _sse("token", {"text": payload})
            else:
                yield _sse("done", payload.model_dump(mode="json"))
    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/graph")
def graph(limit: int = 400):
    """The plant graph for the explorer and the documents view."""
    return _service.graph_snapshot(limit)


@app.get("/health")
def health():
    return {"status": "ok"}
