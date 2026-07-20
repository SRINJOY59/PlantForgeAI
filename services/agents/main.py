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
from plantmind_core.schemas import ChangeProposal, PermitRequest
from pydantic import BaseModel

from agents.reader import AgentReader
from agents.usecases import (
    AgentBroker, ChangeImpact, ComplianceScanner, FieldCopilotAgent,
    InvestigatorAgent, PermitToWorkAgent, ReportGeneratorAgent,
)


class ReportRequest(BaseModel):
    tag: str


_reader: AgentReader | None = None
_bus: RedisBus | None = None
_broker: AgentBroker | None = None


@asynccontextmanager
async def lifespan(app):
    global _reader, _bus, _broker
    _reader = AgentReader.from_settings()
    _bus = RedisBus.from_settings()

    # --- Build pure-provider agents (no broker dependency) ---
    _investigator = InvestigatorAgent(_reader)
    _compliance = ComplianceScanner(_reader)

    # --- Assemble broker and register providers ---
    _broker = (
        AgentBroker()
        .register_investigator(_investigator)
        .register_compliance(_compliance)
    )

    yield
    _reader.close()


app = FastAPI(title="plantmind-agents", lifespan=lifespan)


@app.post("/assess")
async def assess(proposal: ChangeProposal):
    """Impact assessment for a proposed change. Stamped with the graph version
    it was reasoned against: an assessment of a plant that has since changed is
    a different assessment, and the reader deserves to know which one they have.
    """
    agent = ChangeImpact(_reader, broker=_broker)
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
    agent = ChangeImpact(_reader, broker=_broker)
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


@app.post("/permit/draft")
async def draft_permit(request: PermitRequest):
    """Draft a Permit-to-Work for the requested job.

    Walks the isolation boundary of the tagged equipment, surfaces known
    hazards from failure history, maps the governing clauses, and lists
    the procedures the technician must follow — all drawn from the plant's
    own graph, not from generic templates.  Returns a structured WorkPermit
    the permit authority can review and sign.
    """
    agent = PermitToWorkAgent(_reader, broker=_broker)
    result = await agent.draft_permit(request, graph_version=_bus.graph_version())
    return result.model_dump(mode="json")


@app.post("/permit/draft/stream")
async def draft_permit_stream(request: PermitRequest):
    """The same PTW draft, streamed.  Evidence-gathering steps surface live
    ('step' events), the narrative streams token-by-token, and the full
    structured WorkPermit arrives last as a 'done' event.
    """
    agent = PermitToWorkAgent(_reader, broker=_broker)
    version = _bus.graph_version()

    async def events():
        async for kind, payload in agent.draft_permit_stream(request, version):
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
    agent = ReportGeneratorAgent(_reader, broker=_broker)
    graph_version = _bus.graph_version() if _bus else 0
    return await agent.generate_report(request.tag, graph_version=graph_version)


class StartSessionRequest(BaseModel):
    worker_id: str
    work_order_id: str


class UtteranceRequest(BaseModel):
    utterance: str


@app.post("/copilot/session")
async def copilot_create_session(request: StartSessionRequest):
    """Start a voice copilot session, caching SOP steps from Neo4j into Redis.

    When the broker is wired, the session's first step will be prefixed with
    a safety briefing combining compliance flags and failure history.
    """
    agent = FieldCopilotAgent(_reader, _bus, broker=_broker)
    session = await agent.create_session(
        worker_id=request.worker_id,
        work_order_id=request.work_order_id
    )
    return session.model_dump(mode="json")


@app.post("/copilot/{session_id}/utterance")
async def copilot_process_utterance(session_id: str, request: UtteranceRequest):
    """Process a single voice utterance against the active session state."""
    agent = FieldCopilotAgent(_reader, _bus, broker=_broker)
    response = await agent.process_utterance(session_id, request.utterance)
    return response.model_dump(mode="json")


@app.get("/copilot/{session_id}/state")
def copilot_get_state(session_id: str):
    """Get the current state of a copilot session."""
    agent = FieldCopilotAgent(_reader, _bus, broker=_broker)
    session = agent.get_session(session_id)
    if not session:
        return {"status": "not_found"}
    return session.model_dump(mode="json")


@app.get("/health")
def health():
    return {"status": "ok"}
