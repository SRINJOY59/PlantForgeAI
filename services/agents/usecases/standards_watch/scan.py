"""One standards scan, as a standalone command for the cron.

    python -m agents.usecases.standards_watch.scan

The agents runtime also scans on its slow internal clock; this is the same scan
wrapped as a single shot a scheduler (the standards-cron service) fires, and
that a manual trigger can run on demand. It emits standard_revision alerts to
the alert stream, deduped, so the UI's Standards tab picks them up.

Web search is the hard dependency: a standard's current revision is read off the
public internet. It uses the configured LLM's web_search - on Vertex/Gemini that
is Google Search grounding (native generateContent), on OpenRouter it is the
server-side web tool. Either way the watcher reads a live revision rather than
answering from stale training data (a wrong revision sends engineers to
re-inspect equipment for nothing, so guessing is worse than not answering).

First sight of a standard records a baseline and raises nothing - only a move
between two scans is news. So a fresh system shows no deviations on the first
run; the cron catches real revisions as they happen.
"""

from plantmind_core.aio import run_sync
from plantmind_core.bus import RedisBus
from plantmind_core.telemetry import get_logger

log = get_logger("agents.standards.scan")

# A revision is raised once per actual move; the dedup claim outlives a daily
# cron so the same move is not re-announced every day. It clears well before a
# standard would plausibly move again.
_CLAIM_TTL_S = 7 * 24 * 3600


def run_once() -> int:
    """Run one scan, emit any deviations, return how many were raised."""
    from plantmind_core.llm import get_llm

    from agents.reader import AgentReader
    from agents.usecases.standards_watch.source import WebRevisionSource
    from agents.usecases.standards_watch.watcher import StandardsWatcher

    bus = RedisBus.from_settings()
    reader = AgentReader.from_settings()
    # get_llm() carries web_search: Google Search grounding on Vertex/Gemini,
    # the server-side web tool on OpenRouter.
    watcher = StandardsWatcher(reader, bus, WebRevisionSource(get_llm()))

    alerts = run_sync(watcher.scan(bus.graph_version()))
    raised = 0
    for alert in alerts:
        reader.name_citations(alert.citations)
        # claim_alert dedups across the cron, the agents runtime, and a manual
        # trigger, so whichever fires first wins and the others are no-ops
        if bus.claim_alert(alert.fingerprint, ttl_seconds=_CLAIM_TTL_S):
            bus.publish_alert(alert.model_dump_json())
            raised += 1
            log.info("standard deviation raised", title=alert.title)
    log.info("standards scan complete", deviations=raised)
    return raised


def main():
    try:
        run_once()
    except Exception as e:
        # A cron iteration that throws must not crash the loop that schedules it.
        log.warning("standards scan failed", error=str(e)[:200])


if __name__ == "__main__":
    main()
