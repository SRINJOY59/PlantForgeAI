"""The interview's durable state - the topic agenda, what has been covered,
every fact captured, and the running transcript.

SessionMemory is the aggregate root and it is deliberately active-record: it
saves itself after every mutation, so a crash at any turn loses nothing. The
LLM notetaker that turns raw transcript into facts lives next door in
notetaker.py, and the tool-and-prompt 'brain' in brain.py; this file is the
state those act on, plus how it renders itself into the live prompt.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional
import redis

from pydantic import BaseModel, Field

from plantmind_core.telemetry import get_logger
from plantmind_core.config import get_settings

from interview.config import get_config
from interview.context.models import WorkContext

_redis_client = None

def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis_client

log = get_logger("interview.domain.memory")

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
    skills_path: Optional[str] = None
    staging_key: Optional[str] = None
    error: Optional[str] = None
    created_at: str = ""
    notes_cursor: int = 0             # transcript index already digested

    @classmethod
    def create(cls, profile: dict, context: WorkContext) -> "SessionMemory":
        """A session starts with no agenda - it is generated in the background
        so voice can connect immediately - and set_agenda fills it in when the
        LLM returns. Until then the interviewer runs a warm-up (see
        state_prompt)."""
        memory = cls(session_id=uuid.uuid4().hex[:12], profile=profile,
                     context=context,
                     created_at=datetime.now(timezone.utc).isoformat())
        memory.save()
        return memory

    def set_agenda(self, agenda: Agenda):
        """Populate the topic agenda once the (background) LLM call returns.
        Only fills an empty agenda - a live session's topics are never
        clobbered by a late arrival."""
        if self.topics:
            return
        self.topics = [Topic.from_draft(d, i)
                       for i, d in enumerate(agenda.topics[:MAX_TOPICS],
                                             start=1)]
        self.save()

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

    # ---- tool-side mutations (called by the brain's tool handlers) ----

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
        if not self.topics:
            # agenda still generating in the background: open warmly and keep
            # them talking - never try to finish, focused topics are coming
            return ("## INTERVIEW STATE (live - obey strictly)\n"
                    "Your topic agenda is still being prepared. Greet them by "
                    "name, explain briefly that you are here to capture what "
                    "only they know before they leave, and ask ONE broad "
                    "opening question about their role and what they would "
                    "most want a successor to know. Do NOT call "
                    "finish_interview - more focused topics arrive shortly.")

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

    # ---- persistence (active record) ----

    def save(self):
        _get_redis().set(f"interview:session:{self.session_id}", self.model_dump_json(indent=2), ex=86400)

    @classmethod
    def load(cls, session_id: str) -> Optional["SessionMemory"]:
        data = _get_redis().get(f"interview:session:{session_id}")
        if not data:
            return None
        try:
            return cls.model_validate(json.loads(data))
        except Exception as e:
            log.warning("session load failed", session=session_id,
                        error=str(e)[:200])
            return None
