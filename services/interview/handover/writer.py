"""Turns a finished interview into the skills-handover document and ships it.

One class, three steps that a caller runs in order but that fail differently:
generate the markdown from the captured facts, save it to disk as
skills_<employee>.md, and publish it into the document pipeline. The save can
succeed when the pipeline is down, so publish is separate and re-runnable (the
reingest route calls it alone)."""

from datetime import date
from pathlib import Path
import asyncio

from plantmind_core.celeryapp import WorkerApp
from plantmind_core.llm import Tier, get_llm
from plantmind_core.pipeline import stage_and_enqueue
from plantmind_core.storage import ObjectStore
from plantmind_core.telemetry import get_logger

from interview.config import get_config
from interview.domain import SessionMemory
from interview.prompts import SKILLS_PROMPT

log = get_logger("interview.handover.writer")

# beyond this the raw transcript is condensed before the final write-up
MAX_TRANSCRIPT_CHARS = 60_000


def _skills_filename(memory: SessionMemory) -> str:
    employee = memory.profile.get("employee_id") or "unknown"
    return f"skills_{employee}.md"


class SkillsWriter:
    """Generates, saves, and publishes the skills-handover document."""

    def __init__(self, llm=None):
        self._llm = llm or get_llm()

    async def generate(self, memory: SessionMemory) -> str:
        profile = memory.profile
        system = SKILLS_PROMPT.format(
            name=profile.get("full_name") or "Unknown",
            employee_id=profile.get("employee_id") or "n/a",
            job_title=profile.get("job_title") or "n/a",
            date=date.today().isoformat())

        transcript = self._transcript_block(memory)
        if len(transcript) > MAX_TRANSCRIPT_CHARS:
            transcript = await self._condense(transcript)

        user = (f"## Profile\n{memory.context.brief}\n\n"
                f"## Captured knowledge by topic\n{self._facts_block(memory)}"
                f"\n\n## Transcript\n{transcript}")
        return await self._llm.complete(
            [{"role": "system", "content": system},
             {"role": "user", "content": user}],
            tier=Tier.MID, max_tokens=6000, temperature=0.2)

    @staticmethod
    def save(memory: SessionMemory, markdown: str) -> Path:
        folder = get_config().exports_dir / memory.session_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / _skills_filename(memory)
        path.write_text(markdown, encoding="utf-8")
        return path

    @staticmethod
    def publish(memory: SessionMemory, markdown: str):
        """Stage the skills document and enqueue classification (classify ->
        extract -> resolve -> graph). Content-hash dedup upstream makes a
        double call harmless. Returns the staging key, or None if the pipeline
        is unreachable."""
        employee = memory.profile.get("employee_id") or "unknown"
        try:
            store = ObjectStore.from_settings()
            sender = WorkerApp("interview").send
            return stage_and_enqueue(store, sender, _skills_filename(memory),
                                     markdown.encode("utf-8"),
                                     source=f"interview:{employee}")
        except Exception as e:
            log.warning("ingestion unavailable, skills document saved locally "
                        "only", error=str(e)[:200])
            return None

    # ---- internals ----

    @staticmethod
    def _facts_block(memory: SessionMemory) -> str:
        lines = []
        for topic in memory.topics:
            lines.append(f"### {topic.title} [{topic.category}, {topic.status}]")
            if not topic.facts:
                lines.append("- (nothing captured)")
            lines += [f"- {fact}" for fact in topic.facts]
        return "\n".join(lines)

    @staticmethod
    def _transcript_block(memory: SessionMemory) -> str:
        return "\n".join(
            f"{'INTERVIEWER' if t['role'] == 'assistant' else 'EMPLOYEE'}:"
            f" {t['text']}" for t in memory.transcript)

    async def _condense(self, transcript: str) -> str:
        """A long session's transcript is summarised chunk by chunk (CHEAP)
        before the MID writer sees it - facts already live in the topics, so
        only wording and color need to survive."""
        half = MAX_TRANSCRIPT_CHARS // 2
        chunks = [transcript[i:i + half]
                  for i in range(0, len(transcript), half)]
        tasks = []
        for chunk in chunks:
            tasks.append(self._llm.complete(
                [{"role": "system", "content":
                  "Condense this interview transcript slice to its most "
                  "quotable, specific moments. Keep exact numbers, tags and "
                  "names. Plain text."},
                 {"role": "user", "content": chunk}],
                tier=Tier.CHEAP, max_tokens=1024))
        parts = await asyncio.gather(*tasks)
        return "\n".join(parts)
