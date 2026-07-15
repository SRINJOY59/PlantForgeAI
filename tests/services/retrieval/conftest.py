import sys
from pathlib import Path as FsPath

import pytest

sys.path.insert(0, str(FsPath(__file__).resolve().parents[3] / "services"))

from plantmind_core.config import get_settings

from retrieval.models import Path, Step


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def make_path(*hops, confidence=1.0):
    """make_path(("A","CONNECTED_TO","B"), ("B","HAS_FAILURE","C"))"""
    nodes, steps = {}, []
    for src, edge_type, dst in hops:
        nodes.setdefault(src, {"surface": src, "label": "Equipment"})
        nodes.setdefault(dst, {"surface": dst, "label": "Equipment"})
        steps.append(Step(type=edge_type, src=src, dst=dst,
                          props={"confidence": confidence, "doc_id": "d1"}))
    return Path(nodes=nodes, steps=steps)


class FakeReader:
    """Programmable stand-in for GraphReader."""

    def __init__(self):
        self.entities = {}          # surface -> record
        self.paths = []             # returned by paths_between/outward
        self.degrees = {}
        self.doc_chunks = {}        # doc_id -> [chunk dicts]
        self.text_chunks = []       # chunks_containing results
        self.vector_results = []
        self.relations = []

    def entity_by_surface(self, surface):
        return self.entities.get(surface)

    def entities_by_name(self, phrase, limit=3):
        return [e for s, e in self.entities.items()
                if phrase.lower() in s.lower()][:limit]

    def vector_chunks(self, embedding, k=8):
        return self.vector_results[:k]

    def chunks_containing(self, needle, limit=6):
        return self.text_chunks[:limit]

    def chunks_of_doc(self, doc_id):
        return self.doc_chunks.get(doc_id, [])

    def relations_of(self, node_id, types, limit=40):
        return self.relations[:limit]

    def overdue_inspections(self, today):
        return []

    def failure_mode_counts(self, limit=10):
        return []

    def paths_between(self, src, dst, types, max_hops, limit=100):
        return self.paths

    def paths_outward(self, src, labels, types, max_hops, limit=100):
        return self.paths

    def out_degrees(self, node_ids, types):
        return {n: self.degrees.get(n, 1) for n in node_ids}


class FakeLLM:
    def __init__(self, reply="the answer [doc:abc]"):
        self.reply = reply
        self.prompts = []

    async def complete(self, messages, tier=None, max_tokens=None,
                       temperature=0.0, response_format=None):
        self.prompts.append(messages[-1]["content"])
        return self.reply

    async def stream(self, messages, tier=None, max_tokens=None,
                     temperature=0.0):
        self.prompts.append(messages[-1]["content"])
        for word in self.reply.split(" "):
            yield word + " "


class FakeEmbedder:
    async def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]
