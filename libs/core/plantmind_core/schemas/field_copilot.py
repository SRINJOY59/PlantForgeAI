"""Schemas for the Field Copilot (voice-guided SOP execution) use-case.

These live in the shared contracts layer because they cross the
agents <-> gateway wire in JSON: the gateway WebSocket relays the
CopilotResponse straight to the browser, and both services must agree
on the shape.

Design notes
------------
*  spoken_text / display_text split: TTS must never read "[doc:id p3]".
   spoken_text is already stripped; display_text keeps full citations for
   the screen.
*  SessionState.steps is cached in Redis alongside the index so the agent
   never has to re-query the graph for "repeat that".
*  WorkerIntent is an Enum so the classify step is a closed-world choice.
   A new intent requires a code change, which is the right forcing function
   for a safety-critical feature.
*  SessionState.status is a string not an Enum deliberately: the gateway
   relays it as JSON and the UI shows it verbatim ("active", "paused",
   "complete").
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class WorkerIntent(str, Enum):
    """Every spoken command reduces to one of these intents.

    The LLM classifier picks the best fit.  If none fits, QUESTION is the
    safe fallback - it triggers a graph look-up rather than advancing the
    wrong step, which would be a safety event.
    """
    NEXT_STEP        = "NEXT_STEP"        # "done", "next", "move on"
    PREVIOUS_STEP    = "PREVIOUS_STEP"    # "go back", "previous step"
    REPEAT           = "REPEAT"           # "repeat", "say that again"
    QUESTION         = "QUESTION"         # "what is the torque limit?"
    LOG_OBSERVATION  = "LOG_OBSERVATION"  # "note: the valve is leaking"
    START_SESSION    = "START_SESSION"    # "start execution for WO-991"
    PAUSE            = "PAUSE"            # "pause", "hold on"


class SessionState(BaseModel):
    """One field worker's execution session.

    Lives in Redis as JSON; the agent loads it, mutates it, saves it.
    The WebSocket server is stateless: any replica can serve any request
    as long as it can reach Redis.

    steps: the ordered list of SOP steps, cached at session start so
    navigation (next / back / repeat) costs a Redis GET, not a graph query.
    """
    session_id:        str
    worker_id:         str                            # Supabase sub (user ID)
    work_order_id:     str
    sop_doc_id:        str  = ""                      # resolved at session start
    current_step_index: int = 0
    status:            str  = "active"                # active | paused | complete
    steps:             list[str] = Field(default_factory=list)

    @property
    def current_step(self) -> Optional[str]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    @property
    def is_first_step(self) -> bool:
        return self.current_step_index == 0

    @property
    def is_last_step(self) -> bool:
        return self.current_step_index >= len(self.steps) - 1


class CopilotResponse(BaseModel):
    """What the Field Copilot returns after processing one utterance.

    spoken_text  – fed to the browser's SpeechSynthesis API.  Must be
                   clean prose: no Markdown, no citation brackets, no
                   document IDs.  Safety warnings begin with 'WARNING: '.

    display_text – shown on screen.  May include Markdown formatting and
                   citation references such as [SOP-001 p.3].

    intent_detected – what the agent classified the utterance as.

    step_index   – the step number the session is now on (1-based for UI,
                   even though the model stores 0-based internally).

    is_alert_created – True when a LOG_OBSERVATION intent caused a
                       CandidateSubgraph to be queued for graphd.
    """
    spoken_text:      str
    display_text:     str
    intent_detected:  WorkerIntent
    step_index:       int  = 0
    total_steps:      int  = 0
    is_alert_created: bool = False
