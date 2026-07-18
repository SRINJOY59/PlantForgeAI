"""Show the standards watcher raising an alert, end to end.

The watcher compares each governing standard's currently-published revision
against a baseline it remembers in redis. On a real deployment the revision
comes off the open web (WebRevisionSource) on a daily sweep, and an alert fires
the day a standard actually moves - which is exactly why you can't see one on
demand: nothing has moved yet, and first sight only records a baseline.

This makes a move happen. It seeds an older baseline for a couple of standards,
hands the watcher a source that reports a newer revision, and runs the real
scan. Everything past that point is the production path: the StandardsWatcher
class, the graph read that names the affected equipment, dedup by fingerprint,
and publish to the alert stream the UI tails. Only the web fetch is stubbed,
because a live web search is the one part that isn't deterministic.

    python -m tools.standards_demo

Then open Alerts in the app - the standard-revision alerts are there.
"""

import asyncio

from plantmind_core import keys
from plantmind_core.bus import RedisBus

from agents.reader import AgentReader
from agents.usecases.standards_watch import Published, Revision, RevisionSource
from agents.usecases.standards_watch import StandardsWatcher

# standard -> (old baseline we pretend we last saw, the newer revision the web
# now reports). Chosen because each governs several items, so the alert names
# real equipment from the graph.
MOVES = {
    "OISD-STD-129": ("2018 Edition", "2024 Edition"),
    "API-510": ("10th Edition (2014)", "11th Edition (2023)"),
}


class ScriptedSource(RevisionSource):
    """Stands in for WebRevisionSource: returns a fixed 'current' revision so
    the demo is repeatable. A standard we have no script for returns nothing,
    which the watcher correctly treats as 'could not establish' - no alert."""

    async def current(self, standard: str) -> Published:
        move = MOVES.get(standard)
        if not move:
            return Published(revision=Revision(), sources=[])
        _, now = move
        return Published(
            revision=Revision(revision=now, effective_date="2024-01-01",
                              summary="Revised edition published by the issuing body."),
            sources=[{"url": f"https://example.org/standards/{standard.lower()}",
                      "title": f"{standard} — current edition"}])


def _prime(bus: RedisBus):
    """Seed the old baselines and clear any prior alert claims for these moves,
    so the demo produces the same alerts every time it is run."""
    for standard, (old, _) in MOVES.items():
        bus.set_known_revision(standard, old)
    # forget past claims for these fingerprints so a re-run re-raises them
    for standard, (old, new) in MOVES.items():
        bus._r.srem(keys.ALERTED_SET, f"standard:{standard}:{old}->{new}")


def main():
    bus = RedisBus.from_settings()
    reader = AgentReader.from_settings()
    _prime(bus)

    watcher = StandardsWatcher(reader, bus, ScriptedSource())
    alerts = asyncio.run(watcher.scan(bus.graph_version()))

    if not alerts:
        print("no alerts - are the standards in MOVES actually governing "
              "anything in the graph? (check GOVERNED_BY edges)")
        return

    raised = 0
    for alert in alerts:
        reader.name_citations(alert.citations)
        if bus.claim_alert(alert.fingerprint):
            bus.publish_alert(alert.model_dump_json())
            raised += 1
            print(f"\nRAISED: {alert.title}")
            print(f"  {alert.body.splitlines()[0]}")
            eq = [line for line in alert.body.splitlines() if "governed by it" in line]
            if eq:
                print(f"  {eq[0].strip()}")

    print(f"\npublished {raised} standard-revision alert(s) to the stream.")


if __name__ == "__main__":
    main()
