"""The cache short-circuit: a second identical question skips retrieval and
generation entirely."""

import asyncio

import fakeredis

from plantmind_core.cache import AnswerCache

from retrieval.service import RetrievalService
from conftest import FakeEmbedder, FakeLLM, FakeReader


class CountingReader(FakeReader):
    def __init__(self):
        super().__init__()
        self.vector_calls = 0

    def vector_chunks(self, embedding, k=8):
        self.vector_calls += 1
        return self.vector_results[:k]


def service_with_cache():
    reader = CountingReader()
    reader.vector_results = [{"id": "chunk:doc9#c0", "text": "10 barg.",
                              "context": "", "page": None}]
    cache = AnswerCache(fakeredis.FakeRedis(decode_responses=True),
                        threshold=0.95)
    llm = FakeLLM("The set pressure is 10 barg [doc:doc9]")
    return RetrievalService(reader, llm, FakeEmbedder(), cache=cache), reader, llm


def test_second_identical_question_hits_cache():
    service, reader, llm = service_with_cache()

    a1 = asyncio.run(service.ask("what is the set pressure?"))
    a2 = asyncio.run(service.ask("what is the set pressure?"))

    assert a1.text == a2.text
    assert reader.vector_calls == 1          # second ask did no retrieval
    assert len(llm.prompts) == 1             # and no second generation


def test_cache_invalidation_forces_recompute():
    service, reader, _ = service_with_cache()

    asyncio.run(service.ask("what is the set pressure?"))
    # the answer cited doc9 -> a delta on that doc drops it
    service._cache.invalidate(["doc:doc9"])
    asyncio.run(service.ask("what is the set pressure?"))

    assert reader.vector_calls == 2          # recomputed after invalidation
