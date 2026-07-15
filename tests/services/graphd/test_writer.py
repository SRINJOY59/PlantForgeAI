import json

import fakeredis
import pytest

from plantmind_core import keys
from plantmind_core.bus import RedisBus
from plantmind_core.schemas import GraphDelta
from graphd.writer import GraphWriter
from conftest import FakeStore, make_subgraph


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


def push(r, *subgraphs):
    for csg in subgraphs:
        r.rpush(keys.WRITE_BUFFER, csg.model_dump_json())


def test_empty_buffer_writes_nothing(r):
    store = FakeStore()

    stats = GraphWriter(RedisBus(r), store, batch_size=10).flush()

    assert store.batches == []
    assert stats["subgraphs"] == 0
    assert r.get(keys.GRAPH_VERSION) is None
    assert r.xlen(keys.DELTA_STREAM) == 0


def test_flush_commits_batch_bumps_version_and_publishes_delta(r):
    store = FakeStore()
    push(r, make_subgraph(doc_id="doc1"), make_subgraph(doc_id="doc2", tag="P-101B",
                                                        resolved_id="equip:p-101b"))

    stats = GraphWriter(RedisBus(r), store, batch_size=10).flush()

    assert stats["subgraphs"] == 2
    assert len(store.batches) == 1
    _, version = store.batches[0]
    assert version == 1
    assert r.get(keys.GRAPH_VERSION) == "1"

    entries = r.xrange(keys.DELTA_STREAM)
    assert len(entries) == 1
    delta = GraphDelta.model_validate_json(entries[0][1]["payload"])
    assert delta.graph_version == 1
    assert "equip:p-101a" in delta.touched_node_ids
    assert delta.source_doc_ids == ["doc1", "doc2"]


def test_drains_buffer_across_rounds(r):
    store = FakeStore()
    push(r, *[make_subgraph(doc_id=f"doc{i}") for i in range(5)])

    stats = GraphWriter(RedisBus(r), store, batch_size=2).flush()

    assert stats["rounds"] == 3
    assert stats["subgraphs"] == 5
    assert len(store.batches) == 3
    assert int(r.get(keys.GRAPH_VERSION)) == 3
    assert r.llen(keys.WRITE_BUFFER) == 0


def test_malformed_item_goes_to_dlq_rest_committed(r):
    store = FakeStore()
    r.rpush(keys.WRITE_BUFFER, "{not json")
    push(r, make_subgraph())

    stats = GraphWriter(RedisBus(r), store, batch_size=10).flush()

    assert stats["bad"] == 1
    assert stats["subgraphs"] == 1
    assert r.llen(keys.WRITE_DLQ) == 1
    assert len(store.batches) == 1


def test_unresolved_round_parked_in_dlq_not_dropped(r):
    store = FakeStore()
    csg = make_subgraph()
    csg.nodes[0].resolved_id = None
    push(r, csg)

    stats = GraphWriter(RedisBus(r), store, batch_size=10).flush()

    assert stats["bad"] == 1
    assert store.batches == []
    assert r.llen(keys.WRITE_DLQ) == 1
    # parked item is still valid JSON so it can be replayed after the fix
    replayed = json.loads(r.lrange(keys.WRITE_DLQ, 0, -1)[0])
    assert replayed["doc_id"] == "doc1"


def test_skips_when_lock_held(r):
    store = FakeStore()
    push(r, make_subgraph())
    r.set(keys.FLUSH_LOCK, "1")

    stats = GraphWriter(RedisBus(r), store, batch_size=10).flush()

    assert stats == {"skipped": "already flushing"}
    assert r.llen(keys.WRITE_BUFFER) == 1


def test_store_failure_parks_work_and_releases_lock(r):
    store = FakeStore(fail_times=1)
    push(r, make_subgraph())

    stats = GraphWriter(RedisBus(r), store, batch_size=10).flush()

    assert stats["bad"] == 1
    assert r.llen(keys.WRITE_DLQ) == 1        # nothing lost mid-air anymore
    assert r.get(keys.FLUSH_LOCK) is None


def test_poison_subgraph_parked_others_still_committed(r):
    class PoisonStore(FakeStore):
        def write_batch(self, batch, version):
            if "equip:BAD" in batch.node_ids:
                raise RuntimeError("illegal property")
            super().write_batch(batch, version)

    store = PoisonStore()
    poison = make_subgraph(doc_id="doc-bad", tag="BAD", resolved_id="equip:BAD")
    push(r, make_subgraph(doc_id="doc1"), poison,
         make_subgraph(doc_id="doc3", tag="P-101B", resolved_id="equip:p-101b"))

    stats = GraphWriter(RedisBus(r), store, batch_size=10).flush()

    assert stats["bad"] == 1
    assert stats["subgraphs"] == 2                    # the healthy two landed
    committed = {id for batch, _ in store.batches for id in batch.node_ids}
    assert "equip:p-101a" in committed and "equip:p-101b" in committed
    assert "equip:BAD" not in committed
    assert r.llen(keys.WRITE_DLQ) == 1                # culprit parked, not lost


def test_max_rounds_caps_single_invocation(r):
    store = FakeStore()
    push(r, *[make_subgraph(doc_id=f"doc{i}") for i in range(4)])

    stats = GraphWriter(RedisBus(r), store, batch_size=1, max_rounds=2).flush()

    assert stats["rounds"] == 2
    assert r.llen(keys.WRITE_BUFFER) == 2  # next tick picks these up
