"""Noticing when a standard the plant is held to has moved.

A plant is governed by documents it does not own and cannot see change. OISD
revises a standard, IBR amends a rule, and the plant finds out at the next
audit - having inspected fourteen vessels against a revision that was
superseded eight months ago.

The web part is the easy part: anyone can subscribe to a newsletter saying
OISD-STD-129 changed. What the newsletter cannot say is which of *your* vessels
that lands on, and when each was last inspected against it. That comes out of
the graph, and it is why the watch lives here rather than in an inbox.

Two rules hold the line on trust:

  - A revision read on the web never enters the graph. It rides on the alert as
    a WebSource, in its own field, and the watch's memory of it lives in redis.
  - The alert says the standard moved and names who is affected. It never says
    what the new revision requires - that needs the document, and the honest
    next step is a human fetching it.
"""

import re

from plantmind_core.schemas import Alert, Citation, WebSource
from plantmind_core.telemetry import get_logger

log = get_logger("agents.standards.watcher")

_MONTH = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*",
                    re.I)


def _normalize(revision: str) -> str:
    """Collapse a free-text revision to a comparable key.

    The web search is non-deterministic: the same edition comes back as
    "Jul, 2012" one day and "July 2012" the next. Comparing the raw strings
    turns every rephrasing into a false 'the standard moved' alert. This folds
    month words to a stem and drops case, spaces and punctuation, so trivial
    rewordings compare equal; anything the model genuinely worded differently
    still differs and gets the equivalence check upstream."""
    s = _MONTH.sub(lambda m: m.group(1).lower(), revision or "")
    return re.sub(r"[^a-z0-9]", "", s.lower())


class StandardsWatcher:
    """Compares what the web publishes against what we last saw, and reports
    the difference in terms of this plant's equipment."""

    def __init__(self, reader, bus, source):
        self._reader = reader
        self._bus = bus
        self._source = source

    async def scan(self, graph_version: int) -> list:
        alerts = []
        for row in self._reader.governing_standards():
            alert = await self._check(row, graph_version)
            if alert:
                alerts.append(alert)
        return alerts

    async def _check(self, row: dict, graph_version: int):
        standard = row["standard"]
        published = await self._source.current(standard)
        found = published.revision.revision.strip()
        if not found:
            # the search could not establish one. Saying nothing is right:
            # a "we could not check" alert every day is noise that trains
            # people to ignore the feed.
            log.info("no revision established", standard=standard)
            return None

        prior = self._bus.known_revision(standard)
        # Always advance the stored revision to the latest wording, so the next
        # scan compares against what we last saw, not an ever-staler baseline.
        self._bus.set_known_revision(standard, found)

        if prior is None:
            # first sight of this standard. We have no idea whether that
            # revision is new or ten years old, so this is a baseline, not news.
            log.info("standards baseline recorded", standard=standard,
                     revision=found)
            return None
        if _normalize(prior) == _normalize(found):
            return None
        # Normalized strings differ - could be a real move, or a paraphrase the
        # normaliser can't catch ("5th Ed." vs "5th Edition with Addendum 1").
        # Ask the model whether they name the same revision before raising: a
        # false revision alert is the fastest way to get this feed muted.
        if await self._source.same_revision(prior, found):
            log.info("revision reworded, not moved", standard=standard,
                     prior=prior, found=found)
            return None

        return self._alert(row, prior, found, published, graph_version)

    @staticmethod
    def _alert(row, known, found, published, graph_version) -> Alert:
        standard = row["standard"]
        equipment = row.get("equipment") or []
        affected = row.get("affected") or len(equipment)
        listed = ", ".join(equipment[:8])
        if len(equipment) > 8:
            listed += f", and {len(equipment) - 8} more"

        body = (f"{standard} moved from {known} to {found}"
                + (f", effective {published.revision.effective_date}"
                   if published.revision.effective_date else "") + ".")
        if published.revision.summary:
            body += f" Reported change: {published.revision.summary}"
        body += (f"\n\n{affected} item(s) in this plant are governed by it: "
                 f"{listed}.")
        if row.get("last_inspection"):
            body += (f" The most recent inspection recorded against it was "
                     f"{row['last_inspection']}.")
        body += ("\n\nThe revision itself has not been ingested - this is a "
                 "web report, not a document we hold. Fetch the new revision "
                 "and load it to see what actually changed.")

        return Alert(
            kind="standard_revision",
            # warning, never critical: it is an unverified web claim, and the
            # affected equipment is not necessarily unsafe - it is unchecked
            severity="warning",
            title=f"{standard} revised: {known} -> {found}",
            body=body,
            equipment=equipment[0] if len(equipment) == 1 else None,
            citations=[Citation(doc_id=d, snippet="")
                       for d in (row.get("docs") or [])[:3]],
            web_sources=[WebSource(url=s["url"], title=s.get("title", ""))
                         for s in published.sources],
            # the standard and both revisions: raised once per actual move, and
            # again if it moves again
            fingerprint=f"standard:{standard}:{known}->{found}",
            graph_version=graph_version,
            # nothing here was checked against a document we hold
            verified=False,
            unverified_claims=[f"{standard} is now at {found}"])
