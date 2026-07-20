"""Field Copilot prompts — the safety-critical half of the feature.

The most important constraint: every step that contains a safety warning
(words like WARNING, DANGER, CAUTION, HAZARD, HIGH VOLTAGE, HOT SURFACE,
TOXIC, FLAMMABLE, LOCKOUT, TAGOUT) must be prefixed with "WARNING: " in
the spoken_text so the TTS gives the worker an audible heads-up before the
hazard instruction, not after.

kept in its own file so wording changes get a code review, not a grep.
"""

# ── Intent classifier ─────────────────────────────────────────────────────────

CLASSIFY_SYSTEM = """You are a voice command classifier for an industrial plant
field worker.  The worker speaks to you while executing a Standard Operating
Procedure (SOP) with their hands occupied.

Your ONLY task is to classify the worker's utterance into one of these intents:

  NEXT_STEP        – worker is done with current step and wants the next one.
                     Triggers: "done", "next", "move on", "continue", "finished",
                     "ok next step", "proceed", "got it", "check", "complete"
  PREVIOUS_STEP    – worker wants to go back one step.
                     Triggers: "go back", "previous", "repeat previous", "back"
  REPEAT           – worker wants the current step read aloud again.
                     Triggers: "repeat", "say that again", "what did you say",
                     "come again", "once more"
  QUESTION         – worker is asking a factual question about the equipment,
                     a measurement, a specification, or a procedure.
                     Triggers: any question ("what", "how", "where", "why",
                     "which", "should I", "what is the", "how much")
  LOG_OBSERVATION  – worker is dictating an observation to be recorded in the
                     plant knowledge graph.
                     Triggers: "note", "log", "record", "mark down",
                     "note this down", "add this", "observation"
  START_SESSION    – worker is starting a new execution session for a work order.
                     Triggers: "start", "begin", "execute", "open work order"
  PAUSE            – worker needs to pause the session.
                     Triggers: "pause", "hold", "stop", "wait", "break"

Reply with EXACTLY ONE of those intent names — nothing else.
If the utterance fits multiple, prefer the safest: REPEAT > QUESTION > NEXT_STEP.
If in doubt, reply QUESTION."""

CLASSIFY_TASK = "Utterance: {utterance}"


# ── Question answering (inline field Q&A) ────────────────────────────────────

QA_SYSTEM = """You are a field safety engineer advising a technician who is
mid-task in a live process plant.  The technician has asked a question while
executing a Standard Operating Procedure.

Rules that override everything:
1. SAFETY FIRST: If your answer involves a hazard, a pressure limit, a torque
   limit, a temperature limit, an electrical rating, or a lockout/tagout step,
   begin spoken_text with "WARNING: " followed by the limit or instruction.
2. Be SHORT and SPECIFIC.  The worker is in PPE and cannot re-read.  Give one
   concrete answer, not a paragraph.
3. Do NOT invent specifications.  If the tools returned no data, say so.
4. Citation format for display_text: [SOP-name p.N] or [doc-id].
5. Do NOT say "approved" or "safe to proceed" — those are the permit
   authority's words.

After answering, append ONE sentence reminding the worker which step they are on:
"You are currently on step {step_index} of {total_steps}."
"""

QA_TASK = (
    "Work order: {work_order_id}\n"
    "Current SOP step ({step_index}/{total_steps}): {current_step}\n\n"
    "Worker's question: {question}\n\n"
    "Answer concisely using the graph tools available.  Then produce two versions:\n"
    "  spoken_text: plain language, no markdown, no citations, safe for TTS\n"
    "  display_text: same answer with Markdown and document citations\n"
    "Respond as JSON with keys 'spoken_text' and 'display_text'."
)


# ── Observation extractor ────────────────────────────────────────────────────

EXTRACT_SYSTEM = """You are extracting a structured observation from a field
worker's verbal note.  The worker described something they saw on a piece of
plant equipment.

Extract:
  asset_tag:   the equipment identifier (e.g. P-101A, XV-201, FI-303)
               or the most specific equipment name mentioned.
               If no tag is mentioned, use the context tag.
  observation: a concise, factual sentence describing the condition.
               Use present tense. Strip filler words.

Examples:
  Input:  "Note this down: the suction valve XV-101 has severe rust on the body"
  Output: {"asset_tag": "XV-101", "observation": "Severe rust observed on valve body."}

  Input:  "Log: pressure gauge PI-202 is reading zero, looks broken"
  Output: {"asset_tag": "PI-202", "observation": "Pressure gauge reading zero; suspected faulty."}

Reply ONLY with valid JSON.  Never fabricate equipment tags not in the input."""

EXTRACT_TASK = (
    "Context equipment (from current work order): {context_tags}\n"
    "Worker said: {utterance}"
)


def classify_task(utterance: str) -> str:
    return CLASSIFY_TASK.format(utterance=utterance)


def qa_task(work_order_id: str, step_index: int, total_steps: int,
            current_step: str, question: str) -> str:
    return QA_TASK.format(
        work_order_id=work_order_id,
        step_index=step_index + 1,
        total_steps=total_steps,
        current_step=current_step or "(no step loaded)",
        question=question,
    )


def extract_task(utterance: str, context_tags: list[str]) -> str:
    return EXTRACT_TASK.format(
        utterance=utterance,
        context_tags=", ".join(context_tags) if context_tags else "unknown",
    )


# ── Safety warning detection ──────────────────────────────────────────────────

_HAZARD_WORDS = {
    "warning", "danger", "caution", "hazard", "toxic", "flammable",
    "explosive", "lockout", "tagout", "loto", "high voltage", "hot surface",
    "pressurised", "pressurized", "asphyxiation", "confined space",
    "do not", "never", "must not", "stop before",
}


def is_safety_step(text: str) -> bool:
    """True when a step text contains a hazard keyword and spoken_text should
    be prefixed with 'WARNING: '.  Called before sending TTS to the worker."""
    lower = text.lower()
    return any(kw in lower for kw in _HAZARD_WORDS)


def make_spoken(text: str) -> str:
    """Strip Markdown and citations for TTS; prepend WARNING: if needed."""
    import re
    # Remove citation brackets like [doc:abc p.3]
    clean = re.sub(r"\[doc:[^\]]+\]", "", text)
    # Remove Markdown bold/italic
    clean = re.sub(r"[*_`#>]", "", clean)
    # Collapse whitespace
    clean = " ".join(clean.split())
    if is_safety_step(clean) and not clean.startswith("WARNING:"):
        clean = "WARNING: " + clean
    return clean.strip()
