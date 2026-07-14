import asyncio

from plantmind_core.schemas import EdgeType, NodeType
from extraction.manual.extractor import (
    ManualExtractor, Outline, OutlineEntry, strip_page_furniture,
)
from extraction.text.relations import BatchFindings
from conftest import FakeEmbedder, FakeLLM

PAGES = [
    "ACME Pump Systems\n\n1 Introduction\n\nThis manual covers model KSB-4402 "
    "pumps installed as P-101A and P-101B.\n\nPage 1 of 5",
    "ACME Pump Systems\n\nGeneral safety guidance applies throughout.\n\nPage 2 of 5",
    "ACME Pump Systems\n\n2 Maintenance\n\nRoutine maintenance schedule for "
    "the pump units.\n\nPage 3 of 5",
    "ACME Pump Systems\n\n2.1 Seal replacement\n\nReplace the cartridge seal "
    "when leakage exceeds limits. Suction gauge PI-102 must read at least "
    "0.8 barg before restart.\n\nPage 4 of 5",
    "ACME Pump Systems\n\n2.2 Bearing lubrication\n\nGrease bearings every "
    "2000 hours of operation.\n\nPage 5 of 5",
]

OUTLINE = Outline(entries=[
    OutlineEntry(title="1 Introduction", level=1, start_page=1),
    OutlineEntry(title="2 Maintenance", level=1, start_page=3),
    OutlineEntry(title="2.1 Seal replacement", level=2, start_page=4),
    OutlineEntry(title="2.2 Bearing lubrication", level=2, start_page=5),
])


def extract(outline=OUTLINE):
    llm = FakeLLM(outline, *[BatchFindings() for _ in range(5)])
    extractor = ManualExtractor(llm, FakeEmbedder())
    csg = asyncio.run(extractor.extract("doc-man", "hash-man", "manual.pdf",
                                        PAGES))
    return csg, llm


def test_page_furniture_stripped():
    cleaned = strip_page_furniture(PAGES)
    joined = "\n".join(cleaned)
    assert "ACME Pump Systems" not in joined
    assert "Page 1 of 5" not in joined
    assert "cartridge seal" in joined                  # real content survives


def test_outline_becomes_nested_sections():
    csg, _ = extract()

    sections = {n.props["title"]: n for n in csg.nodes
                if n.type == NodeType.SECTION}
    assert set(sections) == {"1 Introduction", "2 Maintenance",
                             "2.1 Seal replacement", "2.2 Bearing lubrication"}

    part_of = {(e.src, e.dst) for e in csg.edges if e.type == EdgeType.PART_OF}
    maint = sections["2 Maintenance"].surface_form
    seal = sections["2.1 Seal replacement"].surface_form
    assert (seal, maint) in part_of                    # child under parent
    assert (maint, "doc-man") in part_of               # chapter under document
    assert sections["2.1 Seal replacement"].props["path"] == \
        "2 Maintenance > 2.1 Seal replacement"


def test_chunks_carry_chapter_path_context_and_page_provenance():
    csg, _ = extract()

    chunk = next(n for n in csg.nodes if n.type == NodeType.CHUNK
                 and "cartridge seal" in n.props["text"])
    assert chunk.props["context"].startswith(
        "From manual.pdf, 2 Maintenance > 2.1 Seal replacement")
    assert chunk.props["page"] == 4
    assert chunk.props["embedding"] == [0.1, 0.2, 0.3]


def test_mentions_cite_the_right_page():
    csg, _ = extract()

    pi102 = next(e for e in csg.edges if e.type == EdgeType.MENTIONED_IN
                 and e.src == "PI-102")
    assert pi102.provenance.page == 4
    p101a = next(e for e in csg.edges if e.type == EdgeType.MENTIONED_IN
                 and e.src == "P-101A")
    assert p101a.provenance.page == 1


def test_regex_fallback_when_llm_outline_fails():
    llm = FakeLLM(RuntimeError("no outline"), *[BatchFindings()] * 5)

    class Failing(FakeLLM):
        async def structured(self, messages, schema, tier=None, max_tokens=4096):
            outcome = self.responses.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    llm = Failing(RuntimeError("no outline"), *[BatchFindings()] * 5)
    extractor = ManualExtractor(llm, FakeEmbedder())
    csg = asyncio.run(extractor.extract("d", "h", "manual.pdf", PAGES))

    titles = {n.props["title"] for n in csg.nodes if n.type == NodeType.SECTION}
    assert any("2.1" in t for t in titles)             # regex found the headings
