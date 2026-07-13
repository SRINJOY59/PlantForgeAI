import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services"))

from plantmind_core.config import get_settings
from plantmind_core.schemas import (
    CandidateEdge, CandidateNode, CandidateSubgraph, EdgeType, NodeType, Provenance,
)


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def make_subgraph(doc_id="doc1", tag="P-101A", resolved_id="equip:p-101a",
                  with_edge=True):
    nodes = [
        CandidateNode(type=NodeType.EQUIPMENT, surface_form=tag,
                      resolved_id=resolved_id),
        CandidateNode(type=NodeType.DOCUMENT, surface_form=doc_id,
                      resolved_id=f"doc:{doc_id}"),
    ]
    edges = []
    if with_edge:
        edges.append(CandidateEdge(
            type=EdgeType.MENTIONED_IN, src=tag, dst=doc_id,
            provenance=Provenance(doc_id=doc_id, page=1,
                                  extractor_version="v1", confidence=0.95),
        ))
    return CandidateSubgraph(doc_id=doc_id, content_hash=f"hash-{doc_id}",
                             nodes=nodes, edges=edges)


class FakeStore:
    def __init__(self, fail_times=0):
        self.batches = []
        self.fail_times = fail_times

    def write_batch(self, batch, version):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("neo4j unavailable")
        self.batches.append((batch, version))
