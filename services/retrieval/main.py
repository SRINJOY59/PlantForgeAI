"""FastAPI adapter for the retrieval service - the service-level Q&A API
that the gateway and the eval runner call. Run locally with:

    uvicorn retrieval.main:app --port 8001
"""

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from strawberry.fastapi import GraphQLRouter

from plantmind_core.schemas import Turn

from retrieval.graphql_reader import GraphQLReader
from retrieval.graphql_schema import schema as graphql_schema, set_reader
from retrieval.service import RetrievalService

_service = None


@asynccontextmanager
async def lifespan(app):
    global _service
    _service = RetrievalService.from_settings()
    set_reader(GraphQLReader.from_settings())
    yield


app = FastAPI(title="plantmind-retrieval", lifespan=lifespan)

# GraphQL endpoint — GraphiQL playground available at GET /graphql
app.include_router(GraphQLRouter(graphql_schema), prefix="/graphql")


class AskRequest(BaseModel):
    question: str
    # the client sends its own thread back; nothing is stored here
    history: list[Turn] = []
    alert_context: str | None = None
    # who is asking - drives the answer's tone/altitude, not its facts. The
    # gateway sets it from the verified JWT role; defaults to engineer.
    persona: str | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/ask")
async def ask(request: AskRequest):
    answer = await _service.ask(request.question, request.history,
                                request.alert_context, request.persona)
    return answer.model_dump(mode="json")


@app.post("/ask/stream")
async def ask_stream(request: AskRequest):
    async def events():
        async for kind, payload in _service.ask_stream(request.question,
                                                       request.history,
                                                       request.alert_context,
                                                       request.persona):
            if kind == "token":
                yield _sse("token", {"text": payload})
            else:
                yield _sse("done", payload.model_dump(mode="json"))
    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/graph")
def graph(limit: int = 400):
    """The plant graph for the explorer and the documents view."""
    return _service.graph_snapshot(limit)


@app.get("/diagnostics/library")
def diagnostics_library():
    """All stored fault modes for the Library view."""
    rows = _service._reader.fault_library()
    # Parse the signature_json inline so the client gets structured data
    library = []
    for r in rows:
        sig_raw = r.get("signature_json")
        sig = None
        if sig_raw:
            import json as _json
            try:
                sig = _json.loads(sig_raw)
            except Exception:
                sig = None
        library.append({
            "id": r.get("id", ""),
            "cause_id": r.get("cause_id"),
            "cause_label": r.get("cause_label", ""),
            "unit_areas": r.get("unit_areas") or [],
            "lead_tag": r.get("lead_tag", ""),
            "deviation_tags": r.get("deviation_tags") or [],
            "severity": r.get("severity", "warning"),
            "source": r.get("source", "sim"),
            "procedure_id": r.get("procedure_id"),
            "procedure_name": r.get("procedure_name"),
            "signature": sig,
        })
    return library


@app.get("/health")
def health():
    return {"status": "ok"}
