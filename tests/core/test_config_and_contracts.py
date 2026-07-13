import json

import pytest
from pydantic import ValidationError

from plantmind_core.config import Settings, get_settings
from plantmind_core.schemas import (
    CandidateEdge, CandidateNode, CandidateSubgraph, EdgeType, NodeType, Provenance,
)
from plantmind_core.telemetry import TokenMeter, get_logger, trace_id_var


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.write_batch_size == 500
    assert s.pathrag_max_hops == 4
    assert "/" in s.llm_mid  # openrouter slugs are vendor/model


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("WRITE_BATCH_SIZE", "50")
    monkeypatch.setenv("LLM_MID", "z-ai/glm-5.2")
    get_settings.cache_clear()

    s = get_settings()

    assert s.write_batch_size == 50
    assert s.llm_mid == "z-ai/glm-5.2"


def _provenance(**overrides):
    fields = dict(doc_id="doc1", page=3, extractor_version="v1", confidence=0.9)
    fields.update(overrides)
    return Provenance(**fields)


def test_candidate_subgraph_roundtrip():
    csg = CandidateSubgraph(
        doc_id="doc1",
        content_hash="abc123",
        nodes=[CandidateNode(type=NodeType.EQUIPMENT, surface_form="P-101A")],
        edges=[CandidateEdge(type=EdgeType.MENTIONED_IN, src="P-101A", dst="doc1",
                             provenance=_provenance())],
    )
    restored = CandidateSubgraph.model_validate_json(csg.model_dump_json())
    assert restored.nodes[0].surface_form == "P-101A"
    assert restored.edges[0].type == EdgeType.MENTIONED_IN


def test_provenance_rejects_confidence_out_of_range():
    with pytest.raises(ValidationError):
        _provenance(confidence=1.5)


def test_unknown_node_type_rejected():
    with pytest.raises(ValidationError):
        CandidateNode(type="Turbine", surface_form="X-1")


def test_logger_emits_json_with_trace_id():
    import io
    import logging
    from plantmind_core.telemetry import _JsonFormatter

    log = get_logger("test")
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(_JsonFormatter())
    logging.getLogger("test").addHandler(handler)
    trace_id_var.set("trace-42")
    try:
        log.info("something happened", tag="P-101A")
    finally:
        logging.getLogger("test").removeHandler(handler)

    record = json.loads(buf.getvalue().strip())
    assert record["msg"] == "something happened"
    assert record["trace"] == "trace-42"
    assert record["tag"] == "P-101A"


def test_token_meter_accumulates():
    meter = TokenMeter()
    meter.record("model-a", 100, 20)
    meter.record("model-a", 50, 10)
    meter.record("model-b", 1, 1)

    snap = meter.snapshot()
    assert snap["model-a"] == {"prompt": 150, "completion": 30, "calls": 2}
    assert snap["model-b"]["calls"] == 1
