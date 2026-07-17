"""The standards watch reads the open web and reports on plant equipment, so
the tests that matter are the ones about restraint: never guess a revision,
never cry wolf on first sight, and never let a web claim look like a document
we hold."""

import pytest

from plantmind_core.schemas import Alert

from agents.usecases.standards_watch import (Published, Revision,
                                             RevisionSource, StandardsWatcher,
                                             WebRevisionSource, _json_of)

STANDARD = "OISD-STD-129"


class FakeReader:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else [{
            "standard": STANDARD,
            "equipment": ["T-301", "V-210", "V-211"],
            "affected": 3,
            "last_inspection": "2026-02-27",
            "docs": ["doc-a", "doc-b"],
        }]

    def governing_standards(self):
        return self.rows


class FakeBus:
    def __init__(self, known=None):
        self.known = known or {}
        self.writes = []

    def known_revision(self, standard):
        return self.known.get(standard)

    def set_known_revision(self, standard, revision):
        self.known[standard] = revision
        self.writes.append((standard, revision))


class FakeSource(RevisionSource):
    def __init__(self, revision="Rev 5", effective="2026-03-15", summary="",
                 sources=None, blow_up=False):
        self._published = Published(
            revision=Revision(revision=revision, effective_date=effective,
                              summary=summary),
            sources=sources if sources is not None
            else [{"url": "https://oisd.gov.in/std-129", "title": "OISD 129"}])
        self._blow_up = blow_up
        self.asked = []

    async def current(self, standard):
        self.asked.append(standard)
        if self._blow_up:
            raise RuntimeError("network is down")
        return self._published


def watcher(source=None, bus=None, reader=None):
    return StandardsWatcher(reader or FakeReader(), bus or FakeBus(),
                            source or FakeSource())


# -- restraint ----------------------------------------------------------------
async def test_first_sight_of_a_standard_records_a_baseline_and_says_nothing():
    # we have no idea whether that revision is new or ten years old
    bus = FakeBus()
    alerts = await watcher(bus=bus).scan(graph_version=7)
    assert alerts == []
    assert bus.known[STANDARD] == "Rev 5"


async def test_an_unchanged_revision_raises_nothing():
    bus = FakeBus({STANDARD: "Rev 5"})
    assert await watcher(bus=bus).scan(graph_version=7) == []


async def test_a_revision_the_search_could_not_establish_raises_nothing():
    # guessing here sends engineers to re-inspect equipment for nothing
    bus = FakeBus({STANDARD: "Rev 4"})
    alerts = await watcher(source=FakeSource(revision=""), bus=bus).scan(7)
    assert alerts == []
    assert bus.writes == [], "an empty answer must not overwrite what we knew"


async def test_a_blank_revision_does_not_clobber_the_baseline():
    bus = FakeBus({STANDARD: "Rev 4"})
    await watcher(source=FakeSource(revision="   "), bus=bus).scan(7)
    assert bus.known[STANDARD] == "Rev 4"


# -- the alert ----------------------------------------------------------------
async def test_a_moved_revision_raises_one_alert():
    bus = FakeBus({STANDARD: "Rev 4"})
    alerts = await watcher(bus=bus).scan(graph_version=7)
    assert len(alerts) == 1
    assert alerts[0].kind == "standard_revision"
    assert "Rev 4" in alerts[0].title and "Rev 5" in alerts[0].title


async def test_the_alert_names_the_equipment_the_graph_says_is_affected():
    # the whole reason this is not a newsletter subscription
    alerts = await watcher(bus=FakeBus({STANDARD: "Rev 4"})).scan(7)
    body = alerts[0].body
    for tag in ("T-301", "V-210", "V-211"):
        assert tag in body
    assert "3 item(s)" in body


async def test_the_alert_carries_the_last_inspection_date():
    alerts = await watcher(bus=FakeBus({STANDARD: "Rev 4"})).scan(7)
    assert "2026-02-27" in alerts[0].body


async def test_a_long_equipment_list_is_summarised_not_dumped():
    reader = FakeReader([{
        "standard": STANDARD, "affected": 14, "last_inspection": "",
        "equipment": [f"V-{200 + i}" for i in range(14)], "docs": [],
    }])
    alerts = await watcher(bus=FakeBus({STANDARD: "Rev 4"}),
                           reader=reader).scan(7)
    assert "and 6 more" in alerts[0].body


async def test_the_alert_says_the_new_revision_is_not_in_the_graph():
    # it must not read as though we know what changed - we do not have the doc
    alerts = await watcher(bus=FakeBus({STANDARD: "Rev 4"})).scan(7)
    assert "not been ingested" in alerts[0].body


# -- trust --------------------------------------------------------------------
async def test_web_sources_are_not_citations():
    # a Citation points at a document we hold; a url is somebody else's claim
    alerts = await watcher(bus=FakeBus({STANDARD: "Rev 4"})).scan(7)
    alert = alerts[0]
    assert [w.url for w in alert.web_sources] == ["https://oisd.gov.in/std-129"]
    assert all(not c.doc_id.startswith("http") for c in alert.citations)
    assert {c.doc_id for c in alert.citations} == {"doc-a", "doc-b"}


async def test_a_web_claim_is_never_marked_verified():
    alerts = await watcher(bus=FakeBus({STANDARD: "Rev 4"})).scan(7)
    assert alerts[0].verified is False
    assert alerts[0].unverified_claims == [f"{STANDARD} is now at Rev 5"]


async def test_severity_stays_at_warning():
    # an unverified web claim is not a critical plant condition
    alerts = await watcher(bus=FakeBus({STANDARD: "Rev 4"})).scan(7)
    assert alerts[0].severity == "warning"


async def test_the_fingerprint_pins_the_move_so_it_raises_once():
    alerts = await watcher(bus=FakeBus({STANDARD: "Rev 4"})).scan(7)
    assert alerts[0].fingerprint == f"standard:{STANDARD}:Rev 4->Rev 5"


async def test_a_second_move_gets_its_own_fingerprint():
    first = await watcher(bus=FakeBus({STANDARD: "Rev 4"})).scan(7)
    second = await watcher(source=FakeSource(revision="Rev 6"),
                           bus=FakeBus({STANDARD: "Rev 5"})).scan(7)
    assert first[0].fingerprint != second[0].fingerprint


async def test_equipment_is_only_set_when_exactly_one_thing_is_affected():
    reader = FakeReader([{"standard": STANDARD, "equipment": ["T-301"],
                          "affected": 1, "last_inspection": "", "docs": []}])
    alerts = await watcher(bus=FakeBus({STANDARD: "Rev 4"}),
                           reader=reader).scan(7)
    assert alerts[0].equipment == "T-301"

    many = await watcher(bus=FakeBus({STANDARD: "Rev 4"})).scan(7)
    assert many[0].equipment is None


# -- the web adapter ----------------------------------------------------------
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
