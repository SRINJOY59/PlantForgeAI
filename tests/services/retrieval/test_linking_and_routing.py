from plantmind_core.schemas import QueryMode

from retrieval.linker import QueryLinker
from retrieval.router import ModeRouter
from conftest import FakeReader


def reader_with_unit100():
    r = FakeReader()
    r.entities = {
        "K-301": {"id": "equip:K-301", "surface": "K-301", "label": "Equipment"},
        "PSV-204": {"id": "inst:PSV-204", "surface": "PSV-204",
                    "label": "Instrument"},
        "OISD-STD-128": {"id": "reg:oisd-std-128", "surface": "OISD-STD-128",
                         "label": "RegulationClause"},
        "Mechanical Seal Replacement": {
            "id": "proc:mechanical-seal-replacement",
            "surface": "Mechanical Seal Replacement", "label": "Procedure"},
    }
    return r


def test_tags_link_exactly():
    linker = QueryLinker(reader_with_unit100())

    seeds = linker.link("Why did K-301 trip and PSV-204 lift?")

    assert [s.node_id for s in seeds] == ["equip:K-301", "inst:PSV-204"]


def test_standards_link_via_name():
    seeds = QueryLinker(reader_with_unit100()).link(
        "which equipment is governed by OISD-STD-128?")
    assert any(s.node_id == "reg:oisd-std-128" for s in seeds)


def test_title_phrase_fallback_when_no_tags():
    seeds = QueryLinker(reader_with_unit100()).link(
        "walk me through the Mechanical Seal Replacement steps")
    assert seeds and seeds[0].label == "Procedure"


def test_router_rules():
    router = ModeRouter()
    seed = object()

    assert router.route("what is a cold work permit?", []) == QueryMode.VECTOR
    assert router.route("show P-101A failure history", [seed]) == QueryMode.LOCAL
    assert router.route("why did K-301 trip?", [seed]) == QueryMode.PATH
    assert router.route("K-301 and PSV-204 relation",
                        [seed, seed]) == QueryMode.PATH
