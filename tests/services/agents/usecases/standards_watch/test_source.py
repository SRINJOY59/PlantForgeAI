"""The web adapter: turning a search reply into a revision, and never letting a
messy reply take the process down with it."""

from agents.usecases.standards_watch import WebRevisionSource
from agents.usecases.standards_watch.source import _json_of

STANDARD = "OISD-STD-129"


class FakeLLM:
    def __init__(self, text, sources=None):
        self.text = text
        self.sources = sources or []

    async def web_search(self, prompt, tier=None, max_tokens=None):
        return self.text, self.sources


async def test_the_web_source_reads_json_out_of_a_fenced_reply():
    llm = FakeLLM('Here you go:\n```json\n{"revision": "Rev 5", '
                  '"effective_date": "2026-03-15", "summary": "x"}\n```',
                  [{"url": "https://oisd.gov.in", "title": "OISD"}])
    published = await WebRevisionSource(llm).current(STANDARD)
    assert published.revision.revision == "Rev 5"
    assert published.sources[0]["url"] == "https://oisd.gov.in"


async def test_the_web_source_survives_a_reply_with_no_json():
    # a model that answers in prose costs us the check, not the process
    published = await WebRevisionSource(FakeLLM("I could not find it.")).current(
        STANDARD)
    assert published.revision.revision == ""


def test_json_of_finds_the_object_inside_prose():
    assert _json_of('blah {"revision": "Rev 5"} trailing') == '{"revision": "Rev 5"}'
