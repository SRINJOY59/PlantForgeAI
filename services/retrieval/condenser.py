"""Rewriting a follow-up into a question that stands on its own.

Two reasons this happens before retrieval rather than inside the answerer.

The first is that every stage downstream reads the question *text*. The linker
regexes tags out of it, the router counts those tags to choose a mode, and the
pathfinder picks edge types from its wording. "What about its sibling?" carries
none of that, so the whole pipeline would see an untagged question and fall
back to vector search over the corpus - the one mode that cannot answer it.
Handing history to the answerer instead would leave all three of them blind.

The second is the answer cache. It is keyed on the question's embedding, and
"what about it?" means nothing on its own: cached raw, one thread's follow-up
would sit on top of every other thread's identical follow-up, and happily serve
an answer about P-101A to someone who was asking about K-301. Condensing first
makes the key specific again - and because two people phrasing the same
follow-up differently condense to the same question, memory raises the hit rate
instead of poisoning it.
"""

from pydantic import BaseModel, Field

from plantmind_core.llm import Tier
from plantmind_core.telemetry import get_logger

log = get_logger("retrieval.condenser")

# a plant conversation refers back a turn or two, not ten; more history is more
# ways to drag a stale tag into a question that has moved on
MAX_TURNS = 4
# enough of an answer to carry the tags it named, without paying for the prose
MAX_ANSWER_CHARS = 400

INSTRUCTIONS = """\
A plant engineer is in a conversation and has just asked something. Decide \
whether it refers back to the conversation, and if it does, rewrite it to be \
understood on its own.

is_follow_up is true ONLY when the question cannot be understood without the \
conversation - it points back with words like "it", "its", "that pump", "the \
same unit", "those failures", or it is a fragment like "why?" or "and the \
sibling?".

is_follow_up is FALSE when the question can be read on its own, even if it \
happens to come after other questions. In particular:
- Asking what a term, unit, symbol or abbreviation MEANS is never a follow-up. \
"what is barg", "what does PSV stand for", "what is cavitation" are general \
questions that stand alone. Do NOT attach them to whatever equipment was \
being discussed.
- Asking about a piece of equipment by its tag is not a follow-up. It already \
says what it is about.

When is_follow_up is false, return the question exactly as it was typed.

When it is true:
- Replace the references with the tags or terms they point at.
- Only use tags that appear in the conversation. Never invent one.
- Keep the engineer's wording and intent. Do not answer it, do not add detail \
they did not ask for, do not make it longer than it needs to be.
"""


class Standalone(BaseModel):
    is_follow_up: bool = Field(
        description="True only if the question cannot be understood without "
                    "the conversation above")
    question: str = Field(
        description="The question rewritten to stand alone. Exactly as typed "
                    "when is_follow_up is false.")


class QuestionCondenser:
    """Turns (follow-up, history) into one self-contained question."""

    def __init__(self, llm, max_turns: int = MAX_TURNS):
        self._llm = llm
        self._max_turns = max_turns

    async def condense(self, question: str, history: list) -> str:
        """-> a question the rest of the pipeline can read on its own.

        Falls back to the question as asked if anything goes wrong: a bad
        rewrite should cost accuracy on one follow-up, never the answer.
        """
        if not history:
            return question                     # first turn: nothing to resolve

        transcript = self._transcript(history)
        try:
            result = await self._llm.structured(
                [{"role": "user", "content":
                  f"{INSTRUCTIONS}\nCONVERSATION SO FAR:\n{transcript}\n\n"
                  f"FOLLOW-UP: {question}"}],
                Standalone, tier=Tier.CHEAP, max_tokens=512)
        except Exception as e:
            log.warning("condense failed, using the question as asked",
                        error=str(e)[:120])
            return question

        # The model has to declare the question referential before we accept a
        # rewrite. Without this it will happily "resolve" a question that was
        # never pointing anywhere: ask "what is barg" after a thread about
        # V-203 and it comes back as "what is the operating pressure of V-203",
        # which links a seed, routes to LOCAL, and confidently answers a
        # question nobody asked.
        if not result.is_follow_up:
            return question

        rewritten = result.question.strip()
        if not rewritten:
            return question
        if rewritten != question:
            log.info("condensed follow-up", original=question,
                     standalone=rewritten)
        return rewritten

    def _transcript(self, history: list) -> str:
        lines = []
        for turn in history[-self._max_turns:]:
            question, answer = _as_turn(turn)
            lines.append(f"Q: {question}")
            if answer:
                clipped = answer[:MAX_ANSWER_CHARS]
                if len(answer) > MAX_ANSWER_CHARS:
                    clipped += "…"
                lines.append(f"A: {clipped}")
        return "\n".join(lines)


def _as_turn(turn) -> tuple:
    """History arrives as Turn models over HTTP and as plain dicts from tests
    and the eval runner."""
    if isinstance(turn, dict):
        return turn.get("question", ""), turn.get("answer", "") or ""
    return turn.question, turn.answer or ""
