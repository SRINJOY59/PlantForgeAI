from plantmind_core.queues import Flow, Routes
from plantmind_core.schemas import CandidateSubgraph, NodeType

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
