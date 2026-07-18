"""The notetaker: a cheap model that distils the raw transcript into topic
facts and coverage, incrementally.

Kept apart from the SessionMemory it writes into so the state model stays free
of LLM concerns. It is cursor-based - only the transcript since the last digest
is read - so a two-hour session costs the same per turn as a five-minute one,
and the distilled state is what the live prompt re-injects to stop the
interviewer repeating questions.
"""

from plantmind_core.llm import Tier
from plantmind_core.telemetry import get_logger

from interview.domain.memory import (COVERED_AT, MAX_TOPICS, NoteUpdate,
                                     SessionMemory, Topic)
from interview.prompts import NOTETAKER_PROMPT

log = get_logger("interview.domain.notetaker")


class Notetaker:
    """Digests transcript into topic facts and coverage. Bound to an LLM so a
    session can hold one and reuse it across the whole conversation."""

    def __init__(self, llm):
        self._llm = llm

    async def digest(self, memory: SessionMemory) -> bool:
        """Distil the un-digested transcript window into topic facts and
        coverage. Returns True when anything changed."""
        window = memory.transcript[memory.notes_cursor:]
        if not window:
            return False
        cursor_target = len(memory.transcript)

        convo = "\n".join(
            f"{'INTERVIEWER' if t['role'] == 'assistant' else 'EMPLOYEE'}:"
            f" {t['text']}" for t in window)
        agenda = "\n".join(
            f"- {t.id} [{t.status}] {t.title}" for t in memory.topics)
        try:
            update = await self._llm.structured(
                [{"role": "system", "content": NOTETAKER_PROMPT},
                 {"role": "user", "content":
                  f"## Topic agenda\n{agenda}\n\n## New transcript\n{convo}"}],
                NoteUpdate, tier=Tier.CHEAP)
        except Exception as e:
            log.warning("notetaker failed", error=str(e)[:200])
            return False

        changed = self._apply(memory, update)
        memory.notes_cursor = cursor_target
        memory.save()
        return changed

    @staticmethod
    def _apply(memory: SessionMemory, update: NoteUpdate) -> bool:
        changed = False
        by_id = {t.id: t for t in memory.topics}
        for tu in update.topic_updates:
            topic = by_id.get(tu.topic_id)
            if topic is None:
                continue
            for fact in tu.new_facts:
                fact = fact.strip()
                if fact and fact not in topic.facts:
                    topic.facts.append(fact)
                    changed = True
            coverage = max(topic.coverage, min(tu.coverage, 1.0))
            if coverage != topic.coverage:
                topic.coverage = coverage
                changed = True
            status = ("covered" if coverage >= COVERED_AT
                      else "partial" if coverage > 0 or topic.facts
                      else topic.status)
            if status != topic.status:
                topic.status = status
                changed = True
        for draft in update.new_topics:
            if len(memory.topics) >= MAX_TOPICS:
                break
            if any(t.title.lower() == draft.title.lower()
                   for t in memory.topics):
                continue
            memory.topics.append(
                Topic.from_draft(draft, len(memory.topics) + 1))
            changed = True
        for hint in update.followup_hints:
            if hint and hint not in memory.followup_hints:
                memory.followup_hints.append(hint)
        memory.followup_hints = memory.followup_hints[-6:]
        return changed
