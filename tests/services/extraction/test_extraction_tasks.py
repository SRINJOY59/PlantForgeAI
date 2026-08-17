from plantmind_core.queues import Flow, Routes
from plantmind_core.schemas import CandidateNode, CandidateSubgraph, NodeType

from extraction.service import ExtractionService
from extraction.workorder.parser import TableParser
from conftest import SAMPLES, FakeObjectStore


def test_parse_handler_reads_store_and_returns_subgraph():
    key = "raw/abc123/work_orders.csv"
    store = FakeObjectStore({key: (SAMPLES / "work_orders.csv").read_bytes()})
    payload = {"doc_id": "abc123", "object_key": key,
               "filename": "work_orders.csv", "content_hash": "hash-full"}

    csg = ExtractionService(store, table=TableParser()).parse_table(payload)

    assert isinstance(csg, CandidateSubgraph)
    assert csg.doc_id == "abc123"
    assert csg.content_hash == "hash-full"
    assert any(n.type == NodeType.WORK_ORDER for n in csg.nodes)

    # the adapter ships every lane's output to the same next stage,
    # and what rides the queue must round-trip through plain json
    assert Flow.after_extraction is Routes.resolve
    reloaded = CandidateSubgraph.model_validate(csg.model_dump(mode="json"))
    assert len(reloaded.nodes) == len(csg.nodes)


def test_run_lane_caches_result_and_serves_cache_hit(monkeypatch):
    import fakeredis
    from plantmind_core.bus import RedisBus
    import extraction.tasks as tasks

    fake_bus = RedisBus(fakeredis.FakeRedis(decode_responses=True))
    monkeypatch.setattr(tasks, "_get_bus", lambda: fake_bus)

    sent_messages = []
    monkeypatch.setattr(tasks.worker, "send", lambda route, msg: sent_messages.append((route, msg)))

    call_count = 0
    sample_csg = CandidateSubgraph(
        doc_id="doc1", content_hash="hash-123",
        nodes=[CandidateNode(type=NodeType.EQUIPMENT, surface_form="P-101")],
        edges=[]
    )

    def dummy_handler(payload):
        nonlocal call_count
        call_count += 1
        return sample_csg

    payload = {"doc_id": "doc1", "content_hash": "hash-123", "filename": "drawing.png"}

    # First run: handler is called and result is cached
    res1 = tasks._run_lane(dummy_handler, payload, "pnid")
    assert res1["status"] == "extracted"
    assert call_count == 1
    assert len(sent_messages) == 1

    # Second run with same content_hash & lane: cache hit, handler NOT called again
    res2 = tasks._run_lane(dummy_handler, payload, "pnid")
    assert res2["status"] == "cache_hit"
    assert call_count == 1  # handler was not called again
    assert len(sent_messages) == 2


def test_run_lane_in_flight_lock_drops_duplicate(monkeypatch):
    import fakeredis
    from plantmind_core.bus import RedisBus
    import extraction.tasks as tasks

    fake_bus = RedisBus(fakeredis.FakeRedis(decode_responses=True))
    monkeypatch.setattr(tasks, "_get_bus", lambda: fake_bus)

    # Pre-acquire lock to simulate concurrent execution by another worker
    fake_bus.acquire_extraction_lock("hash-in-flight", "pnid")

    called = False
    def dummy_handler(payload):
        nonlocal called
        called = True
        return CandidateSubgraph(doc_id="doc2", content_hash="hash-in-flight", nodes=[], edges=[])

    payload = {"doc_id": "doc2", "content_hash": "hash-in-flight", "filename": "test.pdf"}
    res = tasks._run_lane(dummy_handler, payload, "pnid")

    assert res["status"] == "in_flight"
    assert called is False
