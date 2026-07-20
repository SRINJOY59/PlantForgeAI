"""The human door into the agents service.

Everything in consumer.py is triggered by the plant changing - a delta lands, a
timer fires, and an agent reasons about it. This is the same reasoning reached
the other way round: somebody asks. The engine, the tools and the grounding
check are identical; only who started it differs.

It is a separate process from the consumer rather than a thread inside it. The
consumer's job is to never stop tailing the delta stream, and a request that
blocks for thirty seconds on an LLM has no business sharing that loop. Same
image, two commands:

    python -m agents.consumer                        # the plant asks
    uvicorn agents.main:app --port 8002              # a person asks
"""

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from plantmind_core.bus import RedisBus
from plantmind_core.schemas import ChangeProposal
from pydantic import BaseModel

from agents.reader import AgentReader
from agents.usecases import ChangeImpact, ReportGeneratorAgent

class ReportRequest(BaseModel):
    tag: str

_reader = None
_bus = None


@asynccontextmanager
async def lifespan(app):
    global _reader, _bus
    _reader = AgentReader.from_settings()
    _bus = RedisBus.from_settings()
    yield
    _reader.close()


app = FastAPI(title="plantmind-agents", lifespan=lifespan)


@app.post("/assess")
async def assess(proposal: ChangeProposal):
    """Impact assessment for a proposed change. Stamped with the graph version
    it was reasoned against: an assessment of a plant that has since changed is
    a different assessment, and the reader deserves to know which one they have.
    """
    agent = ChangeImpact(_reader)
    result = await agent.assess(proposal, graph_version=_bus.graph_version())
    return result.model_dump(mode="json")


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/assess/stream")
async def assess_stream(proposal: ChangeProposal):
    """The same assessment, streamed. An assessment walks the graph over
    several tool calls before it writes a word - streaming turns that wait into
    something a reviewer can watch: which evidence is being gathered, then the
    assessment as it is written, then the structured envelope at the end."""
    agent = ChangeImpact(_reader)
    version = _bus.graph_version()

    async def events():
        async for kind, payload in agent.assess_stream(proposal, version):
            if kind == "step":
                yield _sse("step", {"tool": payload})
            elif kind == "token":
                yield _sse("token", {"text": payload})
            elif kind == "done":
                yield _sse("done", payload.model_dump(mode="json"))

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/report/generate")
async def generate_report(request: ReportRequest):
    """Generates a comprehensive Markdown report and compiled PDF report
    for the given equipment tag, storing it in MinIO.
    """
    agent = ReportGeneratorAgent(_reader)
    graph_version = _bus.graph_version() if _bus else 0
    return await agent.generate_report(request.tag, graph_version=graph_version)


@app.get("/health")
def health():
    return {"status": "ok"}
