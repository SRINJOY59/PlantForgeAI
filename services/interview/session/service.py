"""The session application service: create (context + agenda), run (voice via
voice/bot.py or the text loop here), end, and finalize (skills document +
ingestion).

It orchestrates the layers - the context builder, the interviewer, the
notetaker, and the handover writer - but holds no interview logic of its own.
The voice and text paths share the same interviewer, so everything it knows can
be exercised without a microphone."""

import asyncio
import json

from plantmind_core.llm import Tier, get_llm
from plantmind_core.telemetry import get_logger

from interview.context import ContextBuilder, InterviewGraphReader
from interview.domain import Agenda, Interviewer, Notetaker, SessionMemory
from interview.handover import SkillsWriter
from interview.prompts import AGENDA_PROMPT

log = get_logger("interview.session.service")


class InterviewService:
    def __init__(self, reader: InterviewGraphReader):
        self._builder = ContextBuilder(reader)
        self._sessions: dict[str, SessionMemory] = {}
        self._text_chats: dict[str, list] = {}      # debug-mode LLM messages
        self._finalizing: set[str] = set()
        # hold strong refs to background agenda tasks - a create_task result
        # that nobody references can be GC'd before it finishes
        self._bg_tasks: set = set()

    @classmethod
    def from_settings(cls) -> "InterviewService":
        return cls(InterviewGraphReader.from_settings())

    # ---- lifecycle ----

    async def create_session(self, profile: dict) -> SessionMemory:
        # build the context (fast: one graph round-trip) and return right away
        # so voice can start connecting; the agenda - a slower LLM call - is
        # generated in the background and injected when it lands.
        context = await self._builder.build(profile)
        memory = SessionMemory.create(profile, context)
        self._sessions[memory.session_id] = memory
        task = asyncio.create_task(self._build_agenda(memory))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        log.info("session created", session=memory.session_id,
                 employee=profile.get("employee_id"))
        return memory

    async def _build_agenda(self, memory: SessionMemory):
        """Generate the topic agenda off the critical path. On failure the
        session simply runs from the brief - a warm-up interview beats a failed
        one - so this never raises into the caller."""
        try:
            agenda = await get_llm().structured(
                [{"role": "system", "content": AGENDA_PROMPT},
                 {"role": "user", "content": memory.context.brief}],
                Agenda, tier=Tier.MID)
            memory.set_agenda(agenda)
            log.info("agenda ready", session=memory.session_id,
                     topics=len(memory.topics))
        except Exception as e:
            log.warning("agenda generation failed - running from the brief",
                        session=memory.session_id, error=str(e)[:200])

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
        """Skills document + ingestion, exactly once. Every end path (agent
        tool, End button, disconnect) converges here."""
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
            await Notetaker(get_llm()).digest(memory)   # capture the last turns
            writer = SkillsWriter()
            markdown = await writer.generate(memory)
            memory.skills_path = str(writer.save(memory, markdown))
            memory.staging_key = writer.publish(memory, markdown)
            memory.status = "done"
            memory.error = None
            log.info("interview finalized", session=memory.session_id,
                     skills=memory.skills_path, staged=bool(memory.staging_key))
        except Exception as e:
            memory.status = "failed"
            memory.error = str(e)[:300]
            log.error("finalize failed", session=memory.session_id,
                      error=memory.error)
        finally:
            memory.save()
            self._finalizing.discard(memory.session_id)

    # ---- text debug loop (same interviewer, no voice stack) ----

    async def text_turn(self, memory: SessionMemory, text: str) -> str:
        llm = get_llm()
        interviewer = Interviewer(memory)
        handlers = interviewer.tool_handlers()
        specs = [{"type": "function", "function": d}
                 for d in Interviewer.TOOL_DEFS]

        messages = self._text_chats.setdefault(
            memory.session_id,
            [{"role": "system", "content": interviewer.system_prompt()}])
        # the state block lives in the system message; refresh it in place
        messages[0] = {"role": "system", "content": interviewer.system_prompt()}
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
            await Notetaker(llm).digest(memory)
        if memory.status == "ending":
            asyncio.create_task(self.finalize(memory))
        return reply
