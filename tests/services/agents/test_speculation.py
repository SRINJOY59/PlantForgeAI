"""The speculative optimisation: a failure delta makes the runtime
pre-fill the answer cache from the investigation it already ran, so the
technician's question is an instant hit."""

import fakeredis

from plantmind_core.bus import RedisBus
from plantmind_core.cache import AnswerCache
from plantmind_core.schemas import Alert, GraphDelta

from agents.consumer import AgentsRuntime
from conftest import FakeAgentReader


class StubInvestigator:
    async def investigate(self, trigger):
        return Alert(kind="failure_pattern", severity="critical",
                     title=f"{trigger.tag} {trigger.mode}",
                     body="Check suction pressure and the strainer first.",
                     equipment=trigger.tag,
                     fingerprint=f"failure:{trigger.tag}:{trigger.mode}:1",
                     graph_version=trigger.graph_version, verified=True)

    async def investigate_reasoned(self, trigger):
        """The consumer drafts a work order off the investigation trace, so the
        double has to hand back a trace as well as the alert. Empty here: these
        tests are about the alert path, and a drafter with nothing to harvest
        still produces a valid (if bare) draft."""
        return await self.investigate(trigger), _Reasoned()


class _Reasoned:
    """Stands in for agents.usecases.base.Reasoned - only the fields the
    work-order drafter reads."""
    answer = "investigated"
    trace = []
    docs = []
    grounding = None


class FakeEmbedder:
    """Distinct-but-deterministic vectors so different questions differ but
    the same question round-trips exactly."""
    async def embed(self, texts):
        return [[float(len(t)), float(sum(map(ord, t)) % 97), 1.0]
                for t in texts]


def seal_reader():
    r = FakeAgentReader()
    r.failures["equip:P-101B"] = [
        {"tag": "P-101B", "mode": "SEAL-LEAK", "count": 1,
         "causes": [], "docs": ["d"]}]
    r.family[("P-101", "SEAL-LEAK")] = [
        {"tag": "P-101A", "count": 3, "causes": ["cavitation"], "docs": ["d"]}]
    return r


def make_runtime():
    redis = fakeredis.FakeRedis(decode_responses=True)
    bus = RedisBus(redis)
    cache = AnswerCache(redis, threshold=0.95)
    rt = AgentsRuntime(bus, seal_reader(), investigator=StubInvestigator(),
                       cache=cache, embedder=FakeEmbedder(),
                       compliance_interval=10_000, block_ms=0)
    return bus, cache, rt


def failure_delta():
    return GraphDelta(graph_version=5, touched_node_ids=["equip:P-101B"],
                      new_edge_types=["HAS_FAILURE"],
                      source_doc_ids=["d"]).model_dump_json()


def test_failure_delta_prefills_answer_cache():
    bus, cache, rt = make_runtime()
    bus.publish_delta(failure_delta())

    rt.tick()

    # the exact question a technician would ask is now a warm hit
    embedder = FakeEmbedder()
    import asyncio
    (q_emb,) = asyncio.run(embedder.embed(
        ["what should I do about p-101b seal-leak?"]))
    hit = cache.get(q_emb)
    assert hit is not None
    assert "strainer" in hit["text"]
    assert hit["confidence"] == "high"


def test_delta_invalidates_dependent_cache_entries():
    bus, cache, rt = make_runtime()
    # a pre-existing cached answer depending on P-101B
    cache.put("old question", [9.0, 9.0, 9.0],
              {"text": "stale", "citations": [], "mode": "local",
               "confidence": "high", "graph_version": 1},
              ["equip:P-101B"])

    bus.publish_delta(GraphDelta(
        graph_version=6, touched_node_ids=["equip:P-101B"],
        new_edge_types=["MENTIONED_IN"], source_doc_ids=["d"]).model_dump_json())
    rt.tick()

    assert cache.get([9.0, 9.0, 9.0]) is None            # stale entry dropped
