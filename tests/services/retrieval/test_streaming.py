import asyncio

from plantmind_core.schemas import Answer, QueryMode

from retrieval.service import RetrievalService
from conftest import FakeEmbedder, FakeLLM, FakeReader


def collect(agen):
    async def run():
        return [x async for x in agen]
    return asyncio.run(run())


def test_ask_stream_yields_tokens_then_done():
    reader = FakeReader()
    reader.vector_results = [{
        "id": "chunk:doc9#chunk0", "text": "PSV-204 set pressure is 10 barg.",
        "context": "", "page": None}]
    llm = FakeLLM("The set pressure is 10 barg [doc:doc9]")
    service = RetrievalService(reader, llm, FakeEmbedder())

    events = collect(service.ask_stream("what is the set pressure?"))

    kinds = [k for k, _ in events]
    assert kinds[-1] == "done"
    assert kinds[:-1] == ["token"] * (len(kinds) - 1)

    streamed = "".join(p for k, p in events if k == "token")
    assert "10 barg" in streamed

    done = events[-1][1]
    assert isinstance(done, Answer)
    assert done.mode == QueryMode.VECTOR
    assert done.citations[0].doc_id == "doc9"      # meta known despite empty text
    assert done.text == ""


def test_stream_and_ask_take_the_same_route():
    reader = FakeReader()
    reader.entities = {"K-301": {"id": "equip:K-301", "surface": "K-301",
                                 "label": "Equipment"}}
    reader.relations = [{"type": "HAS_FAILURE", "src": "equip:K-301",
                         "dst": "fm:trip", "props": {"wo_id": "WO-1"},
                         "other_id": "fm:trip", "other_surface": "TRIP",
                         "other_label": "FailureMode", "other_props": {}}]
    reader.text_chunks = [{"id": "chunk:d#c0", "text": "K-301 tripped.",
                           "context": "", "page": None}]
    llm = FakeLLM("K-301 history [doc:d]")

    answer = asyncio.run(RetrievalService(reader, llm, FakeEmbedder())
                         .ask("tell me about K-301"))
    events = collect(RetrievalService(reader, llm, FakeEmbedder())
                     .ask_stream("tell me about K-301"))

    assert answer.mode == events[-1][1].mode == QueryMode.LOCAL
