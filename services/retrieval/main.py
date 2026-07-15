"""FastAPI adapter for the retrieval service - the service-level API that
the gateway (and the eval runner) call. Run locally with:

    uvicorn retrieval.main:app --port 8001
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
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


@app.post("/ask")
async def ask(request: AskRequest):
    answer = await _service.ask(request.question)
    return answer.model_dump(mode="json")


@app.get("/health")
def health():
    return {"status": "ok"}
