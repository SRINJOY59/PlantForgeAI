"""Session lifecycle: create (context + agenda), run (voice via bot.py or
the text debug loop here), end, finalize (README + ingestion). The voice and
text paths share the same system prompt, tools and memory, so everything the
interviewer 'knows' can be exercised without a microphone."""

import asyncio
import json

from plantmind_core.llm import Tier, get_llm
from plantmind_core.telemetry import get_logger

from interview.context import build_context
from interview.graph_context import InterviewGraphReader
from interview.memory import Agenda, SessionMemory
from interview.prompts import AGENDA_PROMPT, INTERVIEWER_SYSTEM
from interview.readme_gen import generate_readme, ingest_readme, save_readme

log = get_logger("interview.service")

# shared by the Pipecat bot (converted to FunctionSchema) and the text loop
TOOL_DEFS = [
    {"name": "mark_topic_covered",
     "description": "Mark an agenda topic as fully covered once the employee "
                    "has nothing more to add on it.",
     "parameters": {"type": "object", "properties": {
         "topic_id": {"type": "string",
                      "description": "The topic id from INTERVIEW STATE"},
         "summary": {"type": "string",
                     "description": "One line: the key thing learned"}},
         "required": ["topic_id"]}},
    {"name": "add_topic",
     "description": "Add a new topic the employee raised that is worth "
                    "capturing and is not on the agenda.",
     "parameters": {"type": "object", "properties": {
         "title": {"type": "string"},
         "why": {"type": "string",
                 "description": "Why this is worth capturing"}},
         "required": ["title"]}},
    {"name": "finish_interview",
     "description": "End the interview once every topic is covered or the "
                    "employee wants to stop. Say goodbye BEFORE calling this.",
     "parameters": {"type": "object", "properties": {
         "reason": {"type": "string"}},
         "required": []}},
]


def interviewer_system(memory: SessionMemory) -> str:
    p = memory.profile
    return INTERVIEWER_SYSTEM.format(
        name=p.get("full_name") or "there",
        job_title=p.get("job_title") or "engineer",
        home_unit=p.get("home_unit") or "the plant",
        brief=memory.context.brief,
        state=memory.state_prompt())


def make_tool_handlers(memory: SessionMemory) -> dict:
    """name -> fn(**args) -> json-serialisable result. Mutating memory is
    all they do; ending the call is the runner's job (it watches status)."""

    def mark_topic_covered(topic_id: str, summary: str = ""):
        remaining = memory.mark_covered(topic_id, summary)
        if not remaining:
            return {"ok": True, "remaining": [],
                    "note": "all topics covered - wrap up and call "
                            "finish_interview"}
        return {"ok": True, "remaining": remaining}

    def add_topic(title: str, why: str = ""):
        topic = memory.add_topic(title, why)
        if topic is None:
            return {"ok": False, "note": "duplicate or agenda full"}
        return {"ok": True, "topic_id": topic.id}

    def finish_interview(reason: str = ""):
        memory.status = "ending"
        memory.save()
        return {"ok": True, "note": "interview ending - the farewell you "
                                    "just gave is the last thing said"}

    return {"mark_topic_covered": mark_topic_covered,
            "add_topic": add_topic,
            "finish_interview": finish_interview}


class InterviewService:
    def __init__(self, reader: InterviewGraphReader):
        self._reader = reader
        self._sessions: dict[str, SessionMemory] = {}
        self._text_chats: dict[str, list] = {}      # debug-mode LLM messages
        self._finalizing: set[str] = set()

    @classmethod
    def from_settings(cls) -> "InterviewService":
        return cls(InterviewGraphReader.from_settings())

    # ---- lifecycle ----

    async def create_session(self, profile: dict) -> SessionMemory:
        context = await build_context(profile, self._reader)
        agenda = await get_llm().structured(
            [{"role": "system", "content": AGENDA_PROMPT},
             {"role": "user", "content": context.brief}],
            Agenda, tier=Tier.MID)
        memory = SessionMemory.create(profile, context, agenda)
        self._sessions[memory.session_id] = memory
        log.info("session created", session=memory.session_id,
                 topics=len(memory.topics),
                 employee=profile.get("employee_id"))
        return memory

    def get(self, session_id: str) -> SessionMemory | None:
        memory = self._sessions.get(session_id)
        if memory is None:
            memory = SessionMemory.load(session_id)
            if memory is not None:
                self._sessions[session_id] = memory
        return memory

    def request_end(self, memory: SessionMemory):
        if memory.status in ("created", "live"):
            memory.status = "ending"
            memory.save()

    async def finalize(self, memory: SessionMemory):
        """README + ingestion, exactly once. Every end path (agent tool,
        End button, disconnect) converges here."""
        if memory.status in ("generating", "done") \
                or memory.session_id in self._finalizing:
            return
        if not memory.transcript:
            memory.status = "failed"
            memory.error = "no conversation captured"
            memory.save()
            return
        self._finalizing.add(memory.session_id)
        memory.status = "generating"
        memory.save()
        try:
            await memory.digest(get_llm())        # capture the last turns
            markdown = await generate_readme(memory)
            memory.readme_path = str(save_readme(memory, markdown))
            memory.staging_key = ingest_readme(memory, markdown)
            memory.status = "done"
            memory.error = None
            log.info("interview finalized", session=memory.session_id,
                     readme=memory.readme_path, staged=bool(memory.staging_key))
        except Exception as e:
            memory.status = "failed"
            memory.error = str(e)[:300]
            log.error("finalize failed", session=memory.session_id,
                      error=memory.error)
        finally:
            memory.save()
            self._finalizing.discard(memory.session_id)

    # ---- text debug loop (same brain, no voice stack) ----

    async def text_turn(self, memory: SessionMemory, text: str) -> str:
        llm = get_llm()
        handlers = make_tool_handlers(memory)
        specs = [{"type": "function", "function": d} for d in TOOL_DEFS]

        messages = self._text_chats.setdefault(
            memory.session_id,
            [{"role": "system", "content": interviewer_system(memory)}])
        # the state block lives in the system message; refresh it in place
        messages[0] = {"role": "system", "content": interviewer_system(memory)}
        if memory.status == "created":
            memory.status = "live"
            memory.save()

        memory.add_turn("user", text)
        messages.append({"role": "user", "content": text})

        reply = ""
        for _ in range(4):
            msg = await llm.chat_with_tools(messages, specs, tier=Tier.MID)
            calls = getattr(msg, "tool_calls", None)
            if not calls:
                reply = msg.content or ""
                messages.append({"role": "assistant", "content": reply})
                break
            messages.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [{
                    "id": c.id, "type": "function",
                    "function": {"name": c.function.name,
                                 "arguments": c.function.arguments}}
                    for c in calls]})
            for call in calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                handler = handlers.get(call.function.name)
                result = (handler(**args) if handler
                          else {"error": "unknown tool"})
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps(result, default=str)})

        if reply:
            memory.add_turn("assistant", reply)
        if memory.undigested_turns() >= 4:
            await memory.digest(llm)
        if memory.status == "ending":
            asyncio.create_task(self.finalize(memory))
        return reply
