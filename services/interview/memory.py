"""The interview's long memory. The LLM context window holds the recent
conversation; this holds the durable state - the topic agenda, what has been
covered, and every fact captured so far. A cheap 'notetaker' model digests
the transcript incrementally (cursor-based, so a two-hour session costs the
same per turn as a five-minute one) and the distilled state is re-injected
into the live prompt, which is what guarantees no repeated questions."""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

from plantmind_core.llm import Tier
from plantmind_core.telemetry import get_logger

from interview.config import get_config
from interview.context import WorkContext
from interview.prompts import NOTETAKER_PROMPT

log = get_logger("interview.memory")

CATEGORIES = ("role", "projects", "equipment", "tribal", "procedures",
              "handover")
COVERED_AT = 0.8          # coverage score at which a topic counts as done
MAX_TOPICS = 20


class TopicDraft(BaseModel):
    """What the agenda/notetaker LLM emits - ids and status are ours."""
    title: str
    category: str = "tribal"
    rationale: str = ""
    seed_questions: list[str] = []


class Agenda(BaseModel):
    topics: list[TopicDraft]


class Topic(BaseModel):
    id: str
    title: str
    category: str = "tribal"
    rationale: str = ""
    seed_questions: list[str] = []
    status: Literal["pending", "partial", "covered"] = "pending"
    coverage: float = 0.0
    facts: list[str] = []

    @classmethod
    def from_draft(cls, draft: TopicDraft, index: int) -> "Topic":
        category = draft.category if draft.category in CATEGORIES else "tribal"
        return cls(id=f"t{index:02d}", title=draft.title, category=category,
                   rationale=draft.rationale,
                   seed_questions=draft.seed_questions[:4])


class TopicUpdate(BaseModel):
    topic_id: str
    new_facts: list[str] = []
    coverage: float = Field(0.0, ge=0.0, le=1.0)


class NoteUpdate(BaseModel):
    topic_updates: list[TopicUpdate] = []
    new_topics: list[TopicDraft] = []
    followup_hints: list[str] = []


class SessionMemory(BaseModel):
    session_id: str
    profile: dict
    context: WorkContext
    topics: list[Topic] = []
    transcript: list[dict] = []       # {role, text, ts}
    status: Literal["created", "live", "ending", "generating",
                    "done", "failed"] = "created"
    followup_hints: list[str] = []
    readme_path: Optional[str] = None
    staging_key: Optional[str] = None
    error: Optional[str] = None
    created_at: str = ""
    notes_cursor: int = 0             # transcript index already digested

    @classmethod
    def create(cls, profile: dict, context: WorkContext,
               agenda: Agenda) -> "SessionMemory":
        topics = [Topic.from_draft(d, i)
                  for i, d in enumerate(agenda.topics[:MAX_TOPICS], start=1)]
        memory = cls(session_id=uuid.uuid4().hex[:12], profile=profile,
                     context=context, topics=topics,
                     created_at=datetime.now(timezone.utc).isoformat())
        memory.save()
        return memory

    # ---- transcript ----

    def add_turn(self, role: str, text: str):
        text = (text or "").strip()
        if not text:
            return
        self.transcript.append({
            "role": role, "text": text,
            "ts": datetime.now(timezone.utc).isoformat()})
        self.save()

    def undigested_turns(self) -> int:
        return len(self.transcript) - self.notes_cursor

    # ---- notetaker ----

    async def digest(self, llm) -> bool:
        """Distil the un-digested transcript window into topic facts and
        coverage. Returns True when anything changed."""
        window = self.transcript[self.notes_cursor:]
        if not window:
            return False
        cursor_target = len(self.transcript)

        convo = "\n".join(
            f"{'INTERVIEWER' if t['role'] == 'assistant' else 'EMPLOYEE'}:"
            f" {t['text']}" for t in window)
        agenda = "\n".join(
            f"- {t.id} [{t.status}] {t.title}" for t in self.topics)
        try:
            update = await llm.structured(
                [{"role": "system", "content": NOTETAKER_PROMPT},
                 {"role": "user", "content":
                  f"## Topic agenda\n{agenda}\n\n## New transcript\n{convo}"}],
                NoteUpdate, tier=Tier.CHEAP)
        except Exception as e:
            log.warning("notetaker failed", error=str(e)[:200])
            return False

        changed = self._apply(update)
        self.notes_cursor = cursor_target
        self.save()
        return changed

    def _apply(self, update: NoteUpdate) -> bool:
        changed = False
        by_id = {t.id: t for t in self.topics}
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
            if len(self.topics) >= MAX_TOPICS:
                break
            if any(t.title.lower() == draft.title.lower() for t in self.topics):
                continue
            self.topics.append(Topic.from_draft(draft, len(self.topics) + 1))
            changed = True
        for hint in update.followup_hints:
            if hint and hint not in self.followup_hints:
                self.followup_hints.append(hint)
        self.followup_hints = self.followup_hints[-6:]
        return changed

    # ---- tool-side mutations ----

    def mark_covered(self, topic_id: str, summary: str = "") -> list:
        for topic in self.topics:
            if topic.id == topic_id:
                topic.status = "covered"
                topic.coverage = 1.0
                if summary and summary not in topic.facts:
                    topic.facts.append(summary)
        self.save()
        return [t.title for t in self.topics if t.status != "covered"]

    def add_topic(self, title: str, rationale: str = "") -> Optional[Topic]:
        if len(self.topics) >= MAX_TOPICS or not title:
            return None
        if any(t.title.lower() == title.lower() for t in self.topics):
            return None
        topic = Topic.from_draft(
            TopicDraft(title=title, rationale=rationale),
            len(self.topics) + 1)
        self.topics.append(topic)
        self.save()
        return topic

    # ---- prompt state ----

    def all_covered(self) -> bool:
        return bool(self.topics) and all(
            t.status == "covered" for t in self.topics)

    def overall_coverage(self) -> float:
        if not self.topics:
            return 0.0
        return sum(t.coverage for t in self.topics) / len(self.topics)

    def state_prompt(self) -> str:
        """The compact INTERVIEW STATE block re-injected into the live
        system context after every digest. Replaced in place, never
        appended, so the prompt stays ~300 tokens for the whole session."""
        covered = [t for t in self.topics if t.status == "covered"]
        open_topics = [t for t in self.topics if t.status != "covered"]

        lines = ["## INTERVIEW STATE (live - obey strictly)"]
        if covered:
            lines.append("### Already answered - do NOT re-ask any of this")
            for t in covered:
                gist = "; ".join(t.facts[:2]) or "covered"
                lines.append(f"- {t.title}: {gist}")
        if open_topics:
            focus = open_topics[0]
            lines.append(f"### Current focus: {focus.title} ({focus.id})")
            if focus.rationale:
                lines.append(f"why: {focus.rationale}")
            for q in focus.seed_questions[:3]:
                lines.append(f"- possible question: {q}")
            if len(open_topics) > 1:
                lines.append("### Still to cover after that")
                lines += [f"- {t.title} ({t.id})" for t in open_topics[1:]]
        else:
            lines.append("### All topics covered")
            lines.append("Wrap up: summarise what you learned in two spoken "
                         "sentences, thank them, and call finish_interview.")
        if self.followup_hints:
            lines.append("### Follow-up threads worth pulling")
            lines += [f"- {h}" for h in self.followup_hints[-4:]]
        return "\n".join(lines)

    # ---- persistence ----

    def _path(self):
        return get_config().sessions_dir / f"{self.session_id}.json"

    def save(self):
        path = self._path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, session_id: str) -> Optional["SessionMemory"]:
        path = get_config().sessions_dir / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            return cls.model_validate(
                json.loads(path.read_text(encoding="utf-8")))
        except Exception as e:
            log.warning("session load failed", session=session_id,
                        error=str(e)[:200])
            return None
