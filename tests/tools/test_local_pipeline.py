import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from plantmind_core.config import get_settings
from tools.local_pipeline import GraphCollector, LocalPipeline

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_table_file_flows_end_to_end_in_process():
    pipeline = LocalPipeline()          # no llm: table lane only

    result = asyncio.run(pipeline.ingest(
        "work_orders.csv", (SAMPLES / "work_orders.csv").read_bytes()))

    assert result["status"] == "written"
    assert result["kind"] == "table"
    assert result["nodes"] > 20

    (batch, version) = pipeline.store.batches[0]
    assert version == 1
    assert "equip:P-101A" in batch.node_ids          # resolved canonical ids
    assert "wo:WO-2214" in batch.node_ids
    assert "HAS_FAILURE" in batch.edges_by_type


def test_duplicate_content_short_circuits():
    pipeline = LocalPipeline()
    data = (SAMPLES / "work_orders.csv").read_bytes()

    asyncio.run(pipeline.ingest("work_orders.csv", data))
    result = asyncio.run(pipeline.ingest("renamed_copy.csv", data))

    assert result["status"] == "duplicate"
    assert len(pipeline.store.batches) == 1


def test_llm_lane_without_llm_is_skipped_not_crashed():
    pipeline = LocalPipeline()

    result = asyncio.run(pipeline.ingest(
        "sop.md", (SAMPLES / "sop_pump_seal_replacement.md").read_bytes()))

    assert result["status"] == "skipped"
    assert "needs an LLM" in result["reason"]


def test_two_documents_merge_on_shared_equipment():
    pipeline = LocalPipeline()

    asyncio.run(pipeline.ingest(
        "work_orders.csv", (SAMPLES / "work_orders.csv").read_bytes()))
    asyncio.run(pipeline.ingest(
        "inspection_records.csv",
        (SAMPLES / "inspection_records.csv").read_bytes()))

    ids_first = pipeline.store.batches[0][0].node_ids
    ids_second = pipeline.store.batches[1][0].node_ids
    # V-203 appears in both files and resolves to the same canonical id -
    # in a real store the MERGE would land on one node
    assert "equip:V-203" in ids_first and "equip:V-203" in ids_second
