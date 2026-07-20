"""Field Copilot agent — stateful, voice-driven SOP execution.

Unlike every other agent in this service, the Field Copilot is *stateful*:
it remembers which step the worker is on across utterances.  State lives in
Redis (not in the agent instance), so the WebSocket server is stateless and
horizontally scalable — any replica can serve any request.

The agent is never triggered by a delta or a timer.  It only responds to
a person's voice, relayed through the gateway WebSocket.

When wired with an AgentBroker the Field Copilot also:
  - Assembles a safety briefing at session creation time by combining
    compliance flags (ComplianceScanner) and hazard history (InvestigatorAgent)
    for the work order's equipment.  The briefing is prepended to the first
    step so the worker hears it before any hands-on work begins.
"""

import asyncio
import json
import uuid
from typing import TYPE_CHECKING

from plantmind_core.bus import RedisBus
from plantmind_core.keys import COPILOT_SESSION_PREFIX
from plantmind_core.llm import Tier, ToolAgent, get_llm
from plantmind_core.schemas import (
    CandidateNode, CandidateSubgraph, CopilotResponse,
    SessionState, WorkerIntent,
)
from plantmind_core.telemetry import get_logger

from agents import tools
from agents.usecases.field_copilot import prompts

if TYPE_CHECKING:
    from agents.usecases.broker import AgentBroker

log = get_logger("agents.usecases.field_copilot")

# Session TTL in Redis — 8 hours covers a full shift.
SESSION_TTL_S = 8 * 3600


class FieldCopilotAgent:
    """Processes one utterance at a time against a Redis-backed session.

    Optionally accepts an AgentBroker. When wired, the agent fetches a
    combined safety briefing (compliance + failure history) for the work
    order's equipment and prepends it to the first spoken step.
    """

    def __init__(self, reader, bus: RedisBus, llm=None,
                 broker: "AgentBroker | None" = None):
        self._reader = reader
        self._bus = bus
        self._llm = llm or get_llm()
        self._broker = broker

    # ── Session lifecycle ─────────────────────────────────────────────────

    async def create_session(self, worker_id: str,
                             work_order_id: str) -> SessionState:
        """Start a new execution session for a work order.

        Resolves the SOP steps from the graph at session start and caches
        them in Redis.  Subsequent next/back/repeat calls just index into
        this list — no graph query per step.

        When a broker is wired, also fetches a safety briefing (compliance
        flags + hazard history) and prepends it to the first step text.
        """
        sop_rows = await asyncio.to_thread(
            self._reader.sop_steps, work_order_id
        )
        steps = [r["step_text"] for r in sop_rows]
        sop_id = sop_rows[0]["sop_id"] if sop_rows else ""

        # Broker: prepend safety briefing to first step
        if self._broker and steps:
            # Determine equipment tag from the work order
            wo_details = await asyncio.to_thread(
                self._reader.work_order_details, work_order_id
            )
            equipment_tags = wo_details.get("equipment", []) if wo_details else []
            if equipment_tags:
                tag = equipment_tags[0]
                briefing = await self._broker.get_safety_briefing(tag)
                if briefing:
                    steps[0] = briefing + " " + steps[0]
                    log.info("safety briefing prepended to session",
                             work_order=work_order_id, tag=tag)

        session = SessionState(
            session_id=uuid.uuid4().hex[:16],
            worker_id=worker_id,
            work_order_id=work_order_id,
            sop_doc_id=sop_id,
            current_step_index=0,
            status="active",
            steps=steps,
        )
        self._save_session(session)
        log.info("copilot session created",
                 session_id=session.session_id,
                 work_order=work_order_id,
                 steps_loaded=len(steps))
        return session

    def get_session(self, session_id: str) -> SessionState | None:
        key = COPILOT_SESSION_PREFIX + session_id
        raw = self._bus._r.get(key)
        if not raw:
            return None
        return SessionState.model_validate_json(raw)

    def _save_session(self, session: SessionState):
        key = COPILOT_SESSION_PREFIX + session.session_id
        self._bus._r.setex(key, SESSION_TTL_S,
                           session.model_dump_json())

    # ── Utterance processing ──────────────────────────────────────────────

    async def process_utterance(self, session_id: str,
                                utterance: str) -> CopilotResponse:
        session = self.get_session(session_id)
        if session is None:
            return CopilotResponse(
                spoken_text="I could not find an active session. "
                            "Please start a new session first.",
                display_text="Session not found.",
                intent_detected=WorkerIntent.QUESTION,
            )

        # Step 1: classify the utterance into an intent
        intent = await self._classify(utterance)
        log.info("intent classified", session_id=session_id,
                 intent=intent.value, utterance=utterance[:80])

        # Step 2: dispatch to the correct handler
        if intent == WorkerIntent.NEXT_STEP:
            return self._handle_next(session)
        elif intent == WorkerIntent.PREVIOUS_STEP:
            return self._handle_previous(session)
        elif intent == WorkerIntent.REPEAT:
            return self._handle_repeat(session)
        elif intent == WorkerIntent.QUESTION:
            return await self._handle_question(session, utterance)
        elif intent == WorkerIntent.LOG_OBSERVATION:
            return await self._handle_observation(session, utterance)
        elif intent == WorkerIntent.PAUSE:
            return self._handle_pause(session)
        else:
            return self._handle_repeat(session)

    # ── Intent classifier ─────────────────────────────────────────────────

    async def _classify(self, utterance: str) -> WorkerIntent:
        answer = await self._llm.complete(
            [{"role": "system", "content": prompts.CLASSIFY_SYSTEM},
             {"role": "user", "content": prompts.classify_task(utterance)}],
            tier=Tier.CHEAP,
        )
        raw = answer.strip().upper().replace(" ", "_")
        try:
            return WorkerIntent(raw)
        except ValueError:
            # Safe fallback: treat unknown as a question, not a step advance
            return WorkerIntent.QUESTION

    # ── Navigation handlers ───────────────────────────────────────────────

    def _handle_next(self, session: SessionState) -> CopilotResponse:
        if session.is_last_step:
            session.status = "complete"
            self._save_session(session)
            spoken = ("All steps complete. "
                      "Please notify your supervisor for sign-off.")
            return CopilotResponse(
                spoken_text=spoken,
                display_text=spoken,
                intent_detected=WorkerIntent.NEXT_STEP,
                step_index=len(session.steps),
                total_steps=len(session.steps),
            )

        session.current_step_index += 1
        self._save_session(session)
        return self._step_response(session, WorkerIntent.NEXT_STEP)

    def _handle_previous(self, session: SessionState) -> CopilotResponse:
        if session.is_first_step:
            spoken = "You are already on the first step."
            return CopilotResponse(
                spoken_text=spoken,
                display_text=spoken,
                intent_detected=WorkerIntent.PREVIOUS_STEP,
                step_index=1,
                total_steps=len(session.steps),
            )

        session.current_step_index -= 1
        self._save_session(session)
        return self._step_response(session, WorkerIntent.PREVIOUS_STEP)

    def _handle_repeat(self, session: SessionState) -> CopilotResponse:
        return self._step_response(session, WorkerIntent.REPEAT)

    def _handle_pause(self, session: SessionState) -> CopilotResponse:
        session.status = "paused"
        self._save_session(session)
        spoken = ("Session paused. Say 'continue' or 'next step' "
                  "when you are ready to resume.")
        return CopilotResponse(
            spoken_text=spoken,
            display_text=spoken,
            intent_detected=WorkerIntent.PAUSE,
            step_index=session.current_step_index + 1,
            total_steps=len(session.steps),
        )

    def _step_response(self, session: SessionState,
                       intent: WorkerIntent) -> CopilotResponse:
        step_text = session.current_step or "No step available."
        idx = session.current_step_index + 1
        total = len(session.steps)

        spoken = prompts.make_spoken(
            f"Step {idx} of {total}. {step_text}"
        )
        display = f"**Step {idx} / {total}**\n\n{step_text}"

        return CopilotResponse(
            spoken_text=spoken,
            display_text=display,
            intent_detected=intent,
            step_index=idx,
            total_steps=total,
        )

    # ── Question handler ──────────────────────────────────────────────────

    async def _handle_question(self, session: SessionState,
                               question: str) -> CopilotResponse:
        task_text = prompts.qa_task(
            work_order_id=session.work_order_id,
            step_index=session.current_step_index,
            total_steps=len(session.steps),
            current_step=session.current_step or "",
            question=question,
        )
        r = self._reader
        agent = ToolAgent(
            [tools.failure_history(r), tools.fix_procedures(r),
             tools.connected_equipment(r), tools.governing_clauses(r),
             tools.work_orders(r), tools.documents_mentioning(r)],
            tier=Tier.MID, max_steps=4, llm=self._llm,
        )
        result = await agent.run(prompts.QA_SYSTEM, task_text)

        # Try to parse structured JSON from the answer
        spoken, display = self._parse_qa_answer(result.answer)
        spoken = prompts.make_spoken(spoken)

        return CopilotResponse(
            spoken_text=spoken,
            display_text=display,
            intent_detected=WorkerIntent.QUESTION,
            step_index=session.current_step_index + 1,
            total_steps=len(session.steps),
        )

    @staticmethod
    def _parse_qa_answer(answer: str) -> tuple[str, str]:
        """Try to extract spoken_text/display_text from LLM JSON response.
        Falls back to using the raw text for both."""
        try:
            data = json.loads(answer)
            return data.get("spoken_text", answer), data.get("display_text", answer)
        except (json.JSONDecodeError, AttributeError):
            return answer, answer

    # ── Observation handler ───────────────────────────────────────────────

    async def _handle_observation(self, session: SessionState,
                                  utterance: str) -> CopilotResponse:
        # Get context tags from the work order's equipment
        wo_details = await asyncio.to_thread(
            self._reader.work_order_details, session.work_order_id
        )
        context_tags = wo_details.get("equipment", []) if wo_details else []

        # Ask the LLM to extract asset_tag + observation
        extract_text = prompts.extract_task(utterance, context_tags)
        answer = await self._llm.complete(
            [{"role": "system", "content": prompts.EXTRACT_SYSTEM},
             {"role": "user", "content": extract_text}],
            tier=Tier.CHEAP,
        )

        asset_tag, observation = self._parse_observation(answer, context_tags)

        # Queue a CandidateSubgraph for graphd to ingest
        subgraph = CandidateSubgraph(
            nodes=[
                CandidateNode(surface_form=asset_tag, label="Equipment"),
                CandidateNode(surface_form=observation, label="FieldNote"),
            ],
            edges=[],  # graphd resolves the relationship on ingest
        )
        self._bus.queue_subgraph(subgraph.model_dump_json())

        spoken = (f"Noted. I have recorded that {asset_tag} has: "
                  f"{observation}. This will be reviewed by engineering.")
        display = (f"**Observation logged**\n\n"
                   f"- **Asset:** {asset_tag}\n"
                   f"- **Note:** {observation}\n"
                   f"- *Queued for graph ingestion.*")

        log.info("field observation logged",
                 session_id=session.session_id,
                 asset_tag=asset_tag, observation=observation[:100])

        return CopilotResponse(
            spoken_text=spoken,
            display_text=display,
            intent_detected=WorkerIntent.LOG_OBSERVATION,
            step_index=session.current_step_index + 1,
            total_steps=len(session.steps),
            is_alert_created=True,
        )

    @staticmethod
    def _parse_observation(answer: str,
                           context_tags: list[str]) -> tuple[str, str]:
        """Extract (asset_tag, observation) from the LLM JSON response."""
        try:
            data = json.loads(answer)
            tag = data.get("asset_tag", "")
            obs = data.get("observation", "")
            if tag and obs:
                return tag, obs
        except (json.JSONDecodeError, AttributeError):
            pass
        # Fallback: use first context tag and the raw utterance
        tag = context_tags[0] if context_tags else "UNKNOWN"
        return tag, answer.strip()[:200]
