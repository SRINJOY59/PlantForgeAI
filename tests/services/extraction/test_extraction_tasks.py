from plantmind_core.queues import Routes
from plantmind_core.schemas import CandidateSubgraph

from extraction.tasks import run_parse_workorder
from extraction.workorder.parser import TableParser
from conftest import SAMPLES, FakeObjectStore, FakeSender


def test_parse_task_reads_store_and_feeds_resolution():
    key = "raw/abc123/work_orders.csv"
    store = FakeObjectStore({key: (SAMPLES / "work_orders.csv").read_bytes()})
    sender = FakeSender()
    payload = {"doc_id": "abc123", "object_key": key,
               "filename": "work_orders.csv", "content_hash": "hash-full"}

    result = run_parse_workorder(payload, store, TableParser(), sender)

    assert result["status"] == "parsed"
    assert result["nodes"] > 0 and result["edges"] > 0

    route, args, _ = sender.sent[0]
    assert route is Routes.resolve

    # what rides the queue must be plain json-able dict, round-trippable
    shipped = CandidateSubgraph.model_validate(args[0])
    assert shipped.doc_id == "abc123"
    assert shipped.content_hash == "hash-full"
    assert len(shipped.nodes) == result["nodes"]
