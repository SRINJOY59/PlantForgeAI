"""Where 'what revision is this standard at now' comes from.

An interface with one shipped implementation, and the interface earns its keep:
the answer is on the public internet, and a plant network often is not. A site
can point the watcher at an internal mirror without the watcher knowing, and a
test can hand it a scripted answer without touching the web.

A revision read here is a claim, not a fact. Nothing in this module ever writes
to the graph - it returns what the web said and who said it, and the watcher
decides what, if anything, that means for this plant.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel, Field

from plantmind_core.telemetry import get_logger

log = get_logger("agents.standards.source")


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
