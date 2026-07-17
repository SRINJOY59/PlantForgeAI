"""Grounding replaces a badge that was decorative: `verified` only ever existed
on Alert, so the UI's check was undefined === false, and every answer PlantMind
had ever shown claimed to be grounded. These pin the three real states."""

from conftest import FakeEmbedder, FakeLLM, FakeReader

from retrieval.grounding import cited_docs, classify
from retrieval.models import Evidence
from retrieval.service import RetrievalService


def ev(*doc_ids):
    return [Evidence(doc_id=d, text=f"text of {d}", chunk_id=f"chunk:{d}#1")
            for d in doc_ids]


# -- classification -----------------------------------------------------------
def test_an_answer_citing_two_of_our_docs_is_grounded_and_high():
    how, confidence = classify("Three failures [doc:a], all cavitation [doc:b].",
                               ev("a", "b"))
    assert (how, confidence) == ("documents", "high")


def test_one_document_is_grounded_but_only_medium():
    # one source is a fact; two agreeing is corroboration
    assert classify("Three failures [doc:a].", ev("a", "b")) == ("documents", "medium")


def test_an_answer_citing_nothing_is_general_knowledge():
    # "barg is gauge pressure" - true, useful, and not from this plant
    how, _ = classify("Barg is gauge pressure, relative to atmosphere.",
                      ev("a", "b"))
    assert how == "general"


def test_citing_a_document_we_never_showed_it_is_unverified():
    # the id came out of the model, not out of retrieval
    how, confidence = classify("The torque is 45 Nm [doc:made-up].", ev("a"))
    assert (how, confidence) == ("unverified", "low")


def test_one_fabricated_citation_taints_the_whole_answer():
    how, _ = classify("Three failures [doc:a], torque 45 Nm [doc:ghost].",
                      ev("a"))
    assert how == "unverified"


def test_confidence_no_longer_tracks_how_much_we_fetched():
    # the old rule was len(evidence) >= 2 -> high. This is the exact shape of
    # the bug: two chunks retrieved, none of them used.
    how, confidence = classify("I could not find that.", ev("a", "b"))
    assert (how, confidence) != ("documents", "high")
    assert how == "general"


def test_a_page_qualified_citation_is_read():
    assert cited_docs("see [doc:abc p4] for the step") == {"abc"}


def test_an_empty_answer_cites_nothing():
    assert cited_docs("") == set()
    assert cited_docs(None) == set()


# -- what reaches the answer --------------------------------------------------
async def test_only_the_documents_the_answer_used_are_listed_as_sources():
    # listing every chunk retrieval happened to fetch is what made an
    # ungrounded answer look cited
    reader = FakeReader()
    reader.vector_results = [
        {"id": "chunk:a#1", "text": "relevant", "context": "", "page": 1},
        {"id": "chunk:b#1", "text": "not relevant", "context": "", "page": 1},
    ]
    svc = RetrievalService(reader, FakeLLM("the answer [doc:a]"),
                           FakeEmbedder())
    answer = await svc.ask("how many seal failures has P-101A had?")
    assert [c.doc_id for c in answer.citations] == ["a"]


async def test_a_general_answer_lists_no_sources_at_all():
    reader = FakeReader()
    reader.vector_results = [
        {"id": "chunk:a#1", "text": "psv setpoints", "context": "", "page": 1},
        {"id": "chunk:b#1", "text": "more setpoints", "context": "", "page": 1},
    ]
    svc = RetrievalService(reader, FakeLLM("Barg is gauge pressure."),
                           FakeEmbedder())
    answer = await svc.ask("what is barg?")
    assert answer.citations == []
    assert answer.grounding == "general"
    assert answer.confidence == "medium"


async def test_grounding_survives_the_streaming_path():
    # build_meta used to be handed an empty string, which would classify every
    # streamed answer as general
    reader = FakeReader()
    reader.vector_results = [{"id": "chunk:a#1", "text": "t", "context": "",
                              "page": 1}]
    svc = RetrievalService(reader, FakeLLM("the answer [doc:a]"),
                           FakeEmbedder())
    events = [e async for e in svc.ask_stream("how many failures on P-101A?")]
    kind, answer = events[-1]
    assert kind == "done"
    assert answer.text.strip() == "the answer [doc:a]"
    assert answer.grounding == "documents"
