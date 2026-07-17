import asyncio

from plantmind_core.schemas import QueryMode

from retrieval.service import RetrievalService
from conftest import FakeEmbedder, FakeLLM, FakeReader, make_path

CHUNK = {"id": "chunk:doc14#chunk2",
         "text": "Pressure in V-203 rose from 6.2 to 9.8 barg; PSV-204 lifted "
                 "at 14:26 and discharged to flare.",
         "context": "From incident_report_IR-2026-014.md, section Timeline: ",
         "page": None, "start": 100, "end": 220}


def k301_reader():
    r = FakeReader()
    r.entities = {
        "K-301": {"id": "equip:K-301", "surface": "K-301", "label": "Equipment"},
        "PSV-204": {"id": "inst:PSV-204", "surface": "PSV-204",
                    "label": "Instrument"},
    }
    r.paths = [make_path(("equip:K-301", "CONNECTED_TO", "equip:V-203"),
                         ("equip:V-203", "CONNECTED_TO", "inst:PSV-204"))]
    r.degrees = {"equip:K-301": 3, "equip:V-203": 3, "inst:PSV-204": 1}
    r.doc_chunks = {"d1": [CHUNK]}
    return r


def ask(reader, question, llm=None):
    service = RetrievalService(reader, llm or FakeLLM(), FakeEmbedder())
    return asyncio.run(service.ask(question))


def test_causal_question_answers_through_paths():
    llm = FakeLLM("Yes - vapour backs up into V-203 and PSV-204 lifts [doc:d1]")

    answer = ask(k301_reader(), "Could a K-301 trip cause PSV-204 to lift?", llm)

    assert answer.mode == QueryMode.PATH
    assert answer.citations and answer.citations[0].doc_id == "d1"
    assert answer.confidence in ("high", "medium")

    prompt = llm.prompts[0]
    assert "GRAPH PATHS" in prompt
    assert "(K-301) -CONNECTED_TO-> (V-203)" in prompt.replace(
        "equip:", "").replace("inst:", "")
    assert "PSV-204 lifted" in prompt                # evidence chunk included


def test_no_seeds_falls_to_vector_mode():
    reader = FakeReader()
    reader.vector_results = [dict(CHUNK)]
    # cite the doc the chunk actually came from: a source is listed because the
    # answer leaned on it, not because retrieval happened to fetch it
    llm = FakeLLM("It discharges to flare [doc:doc14]")

    answer = ask(reader, "what happens when a relief valve lifts?", llm)

    assert answer.mode == QueryMode.VECTOR
    assert answer.citations[0].doc_id == "doc14"     # parsed from chunk id
    assert answer.grounding == "documents"


def test_single_seed_uses_local_mode():
    reader = k301_reader()
    reader.relations = [{
        "type": "HAS_FAILURE", "src": "equip:K-301", "dst": "fm:trip",
        "props": {"wo_id": "WO-2245", "date": "2026-03-03"},
        "other_id": "fm:trip", "other_surface": "TRIP",
        "other_label": "FailureMode"}]
    reader.text_chunks = [dict(CHUNK)]
    llm = FakeLLM()

    answer = ask(reader, "tell me about K-301", llm)

    assert answer.mode == QueryMode.LOCAL
    prompt = llm.prompts[0]
    assert "EVERYTHING THE GRAPH KNOWS ABOUT K-301" in prompt
    assert "WO-2245" in prompt                       # edge props surfaced


def test_path_mode_without_paths_degrades_to_vector():
    reader = k301_reader()
    reader.paths = []                                # graph has no route
    reader.vector_results = [dict(CHUNK)]
    llm = FakeLLM("PSV-204 lifted and discharged to flare [doc:doc14]")

    answer = ask(reader, "Could a K-301 trip cause PSV-204 to lift?", llm)

    assert answer.mode == QueryMode.VECTOR           # honest fallback
    assert answer.citations
