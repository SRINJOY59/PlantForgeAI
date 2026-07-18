"""Turns a finished interview into the handover README: generated from the
captured facts (transcript only for color), saved under data/interviews/
exports/, and pushed into the ingestion pipeline so the knowledge becomes
queryable like any other plant document."""

from datetime import date
from pathlib import Path

from plantmind_core.celeryapp import WorkerApp
from plantmind_core.llm import Tier, get_llm
from plantmind_core.pipeline import stage_and_enqueue
from plantmind_core.storage import ObjectStore
from plantmind_core.telemetry import get_logger

from interview.config import get_config
from interview.memory import SessionMemory
from interview.prompts import README_PROMPT

log = get_logger("interview.readme")

# beyond this the raw transcript is condensed before the final write-up
MAX_TRANSCRIPT_CHARS = 60_000


def _facts_block(memory: SessionMemory) -> str:
    lines = []
    for topic in memory.topics:
        lines.append(f"### {topic.title} [{topic.category}, {topic.status}]")
        if not topic.facts:
            lines.append("- (nothing captured)")
        lines += [f"- {fact}" for fact in topic.facts]
    return "\n".join(lines)


def _transcript_block(memory: SessionMemory) -> str:
    return "\n".join(
        f"{'INTERVIEWER' if t['role'] == 'assistant' else 'EMPLOYEE'}:"
        f" {t['text']}" for t in memory.transcript)


async def _condense(transcript: str, llm) -> str:
    """A long session's transcript is summarised chunk by chunk (CHEAP)
    before the MID writer sees it - facts already live in the topics, so
    only wording and color need to survive."""
    chunks = [transcript[i:i + MAX_TRANSCRIPT_CHARS // 2]
              for i in range(0, len(transcript), MAX_TRANSCRIPT_CHARS // 2)]
    parts = []
    for chunk in chunks:
        parts.append(await llm.complete(
            [{"role": "system", "content":
              "Condense this interview transcript slice to its most "
              "quotable, specific moments. Keep exact numbers, tags and "
              "names. Plain text."},
             {"role": "user", "content": chunk}],
            tier=Tier.CHEAP, max_tokens=1024))
    return "\n".join(parts)


async def generate_readme(memory: SessionMemory) -> str:
    llm = get_llm()
    profile = memory.profile
    system = README_PROMPT.format(
        name=profile.get("full_name") or "Unknown",
        employee_id=profile.get("employee_id") or "n/a",
        job_title=profile.get("job_title") or "n/a",
        date=date.today().isoformat())

    transcript = _transcript_block(memory)
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = await _condense(transcript, llm)

    user = (f"## Profile\n{memory.context.brief}\n\n"
            f"## Captured knowledge by topic\n{_facts_block(memory)}\n\n"
            f"## Transcript\n{transcript}")
    return await llm.complete(
        [{"role": "system", "content": system},
         {"role": "user", "content": user}],
        tier=Tier.MID, max_tokens=6000, temperature=0.2)


def save_readme(memory: SessionMemory, markdown: str) -> Path:
    folder = get_config().exports_dir / memory.session_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "README.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def ingest_readme(memory: SessionMemory, markdown: str):
    """Push the README through the normal document pipeline (classify ->
    extract -> resolve -> graph). Content-hash dedup upstream makes a
    double call harmless. Returns the staging key, or None if the
    pipeline infrastructure is unreachable."""
    employee = memory.profile.get("employee_id") or "unknown"
    filename = f"interview_{employee}_{date.today().isoformat()}.md"
    try:
        store = ObjectStore.from_settings()
        sender = WorkerApp("interview").send
        return stage_and_enqueue(store, sender, filename,
                                 markdown.encode("utf-8"),
                                 source=f"interview:{employee}")
    except Exception as e:
        log.warning("ingestion unavailable, README saved locally only",
                    error=str(e)[:200])
        return None
