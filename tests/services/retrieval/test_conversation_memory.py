"""Memory at the service level.

The load-bearing claim is that condensing happens *before* the cache key is
computed. Cache first and "what about it?" becomes a key that means nothing,
shared by every thread that ever says it - which is not a slow answer, it is a
confidently wrong one about someone else's pump.
"""

from conftest import FakeEmbedder, FakeLLM, FakeReader

from plantmind_core.schemas import Turn

from retrieval.service import RetrievalService


class TextEmbedder:
    """An embedding that depends on the text, so two questions landing on one
    cache key is detectable rather than baked in."""

    async def embed(self, texts):
        return [[float(len(t)), float(sum(map(ord, t)) % 997), 0.0]
                for t in texts]


class FakeCache:
    def __init__(self):
        self.entries = {}
        self.hits = 0

    def get(self, embedding):
        hit = self.entries.get(tuple(embedding))
        if hit:
            self.hits += 1
        return hit

    def put(self, question, embedding, answer, cited):
        self.entries[tuple(embedding)] = answer


class TagEchoLLM(FakeLLM):
    """Condenses by naming whichever tag it can see in the conversation - a
    crude stand-in for the real rewrite, but enough to tell the threads apart."""

    async def structured(self, messages, schema, tier=None, max_tokens=None):
        prompt = messages[-1]["content"]
        tag = "P-101A" if "P-101A" in prompt else "K-301"
        return schema(is_follow_up=True,
                      question=f"what failures has {tag} had?")


def service(llm=None, cache=None, embedder=None):
    return RetrievalService(FakeReader(), llm or FakeLLM(),
                            embedder or FakeEmbedder(), cache=cache)


async def test_two_threads_asking_what_about_it_do_not_share_a_cache_entry():
    cache = FakeCache()
    svc = service(llm=TagEchoLLM(), cache=cache, embedder=TextEmbedder())

    await svc.ask("what about it?",
                  [Turn(question="seal failures on P-101A?", answer="Three.")])
    await svc.ask("what about it?",
                  [Turn(question="vibration on K-301?", answer="Two.")])

    assert len(cache.entries) == 2, (
        "the two threads condensed to different questions and must occupy "
        "different cache keys")
    assert cache.hits == 0, "neither thread may be served the other's answer"


async def test_identical_standalone_questions_still_share_a_cache_entry():
    # the control for the test above: it is condensing that separates those
    # threads, not the cache having stopped working
    cache = FakeCache()
    svc = service(cache=cache, embedder=TextEmbedder())

    await svc.ask("how many seal failures has P-101A had?")
    await svc.ask("how many seal failures has P-101A had?")

    assert len(cache.entries) == 1
    assert cache.hits == 1


async def test_two_phrasings_of_a_follow_up_condense_onto_one_cache_entry():
    # memory raising the hit rate rather than costing it: different words,
    # same resolved question
    cache = FakeCache()
    svc = service(llm=TagEchoLLM(), cache=cache, embedder=TextEmbedder())

    await svc.ask("what about it?",
                  [Turn(question="seal failures on P-101A?", answer="Three.")])
    await svc.ask("and that one?",
                  [Turn(question="tell me about P-101A", answer="A pump.")])

    assert len(cache.entries) == 1
    assert cache.hits == 1


async def test_a_first_question_costs_no_condense_call():
    llm = FakeLLM()
    await service(llm=llm).ask("how many seal failures has P-101A had?")
    assert not any("FOLLOW-UP" in p for p in llm.prompts), \
        "a question with no history must not pay for a rewrite"


async def test_the_pipeline_sees_the_condensed_question_not_the_follow_up():
    # the whole point: the linker regexes tags out of the question text, so it
    # has to be handed the resolved one
    llm = TagEchoLLM()
    svc = service(llm=llm, embedder=TextEmbedder())
    await svc.ask("what about it?",
                  [Turn(question="seal failures on P-101A?", answer="Three.")])
    answering = llm.prompts[-1]
    assert "what failures has P-101A had?" in answering
    assert "what about it?" not in answering


async def test_streaming_carries_history_too():
    llm = TagEchoLLM()
    svc = service(llm=llm, embedder=TextEmbedder())
    events = [e async for e in svc.ask_stream(
        "what about it?",
        [Turn(question="vibration on K-301?", answer="Two.")])]

    assert events[-1][0] == "done"
    assert any("what failures has K-301 had?" in p for p in llm.prompts)


async def test_history_defaults_to_none_so_old_callers_still_work():
    # the eval runner and the agents service call ask() with one argument
    answer = await service().ask("how many seal failures has P-101A had?")
    assert answer.text
