"""Watching the standards the plant is held to, and noticing when one moves.

A plant is governed by documents it does not own and cannot see change. OISD
revises a standard, IBR amends a rule, and the plant finds out at the next
audit - having inspected fourteen vessels against a revision that was
superseded eight months ago.

The web part of this is the boring part: anyone can subscribe to a newsletter
saying OISD-STD-129 changed. What the newsletter cannot say is which of *your*
vessels that lands on, and when each was last inspected against it. That comes
out of the graph, and it is why this lives here.

Two rules hold the line on trust:

  - A revision we read on the web never enters the graph. Every fact in there
    traces to a document we hold and parsed; a web page is somebody else's
    claim about a document we do not have. It rides on the alert as a
    WebSource, in its own field, and the watch's memory of it lives in redis.

  - The alert says the standard moved and names who is affected. It never says
    what the new revision requires - that needs the document, and the honest
    next step is a human fetching it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel, Field

from plantmind_core.schemas import Alert, Citation, WebSource
from plantmind_core.telemetry import get_logger

log = get_logger("agents.standards")


class Revision(BaseModel):
    """What the web says a standard is currently at."""
    revision: str = Field(default="",
                          description="Current revision or edition, e.g. "
                                      "'Rev 5' or '2026 edition'. Empty if "
                                      "it cannot be established.")
    effective_date: str = Field(default="",
                                description="ISO date it took effect, if stated")
    summary: str = Field(default="",
                         description="One line on what changed, if stated")


@dataclass
class Published:
    revision: Revision
    sources: list          # [{'url', 'title'}]


class RevisionSource(ABC):
    """Where 'what revision is this standard at now' comes from. An interface
    because the answer is on the public internet, and a plant network often is
    not - a site can point this at an internal mirror without the watcher
    knowing."""

    @abstractmethod
    async def current(self, standard: str) -> Published:
        ...


PROMPT = """\
What is the current published revision of the engineering standard "{standard}"?

Answer only from what the search results actually state. If they do not \
establish a current revision, leave revision empty rather than guessing - a \
wrong revision here sends engineers to re-inspect equipment for nothing.

Reply as a single JSON object, no prose:
{{"revision": "...", "effective_date": "YYYY-MM-DD or empty", "summary": "..."}}
"""


class WebRevisionSource(RevisionSource):
    """Asks openrouter's web search what a standard is at now."""

    def __init__(self, llm):
        self._llm = llm

    async def current(self, standard: str) -> Published:
        text, sources = await self._llm.web_search(PROMPT.format(standard=standard))
        try:
            revision = Revision.model_validate_json(_json_of(text))
        except Exception as e:
            log.warning("could not read a revision out of the search reply",
                        standard=standard, error=str(e)[:120])
            return Published(revision=Revision(), sources=sources)
        return Published(revision=revision, sources=sources)


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

        known = self._bus.known_revision(standard)
        self._bus.set_known_revision(standard, found)

        if known is None:
            # first sight of this standard. We have no idea whether that
            # revision is new or ten years old, so this is a baseline, not news.
            log.info("standards baseline recorded", standard=standard,
                     revision=found)
            return None
        if known == found:
            return None

        return self._alert(row, known, found, published, graph_version)

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


def _json_of(text: str) -> str:
    """Web-search replies tend to arrive with prose or fences around the json
    however firmly the prompt asks otherwise."""
    text = text.strip()
    if "```" in text:
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


