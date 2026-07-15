import pytest

from plantmind_core.schemas import Provenance
from graphd.batching import group_batch, prov_hash
from conftest import make_subgraph


def test_groups_nodes_by_label_and_edges_by_type():
    batch = group_batch([make_subgraph()])

    assert set(batch.nodes_by_label) == {"Equipment", "Document"}
    assert set(batch.edges_by_type) == {"MENTIONED_IN"}
    assert batch.node_ids == {"equip:p-101a", "doc:doc1"}
    assert batch.doc_ids == {"doc1"}


def test_edge_endpoints_translated_to_resolved_ids():
    batch = group_batch([make_subgraph()])

    edge = batch.edges_by_type["MENTIONED_IN"][0]
    assert edge["src"] == "equip:p-101a"
    assert edge["dst"] == "doc:doc1"
    assert edge["props"]["doc_id"] == "doc1"
    assert edge["props"]["confidence"] == 0.95


def test_unknown_endpoint_passes_through_as_canonical_id():
    csg = make_subgraph()
    csg.edges[0].dst = "equip:preexisting-node"

    batch = group_batch([csg])

    assert batch.edges_by_type["MENTIONED_IN"][0]["dst"] == "equip:preexisting-node"


def test_same_node_across_docs_merges_props_once():
    a = make_subgraph(doc_id="doc1")
    b = make_subgraph(doc_id="doc2")
    b.nodes[0].props = {"unit": "100"}

    batch = group_batch([a, b])

    rows = batch.nodes_by_label["Equipment"]
    assert len(rows) == 1
    assert rows[0]["props"]["unit"] == "100"
    assert batch.doc_ids == {"doc1", "doc2"}


def test_unresolved_node_raises():
    csg = make_subgraph()
    csg.nodes[0].resolved_id = None

    with pytest.raises(ValueError, match="unresolved"):
        group_batch([csg])


def test_props_are_neo4j_safe():
    from graphd.batching import clean_props

    cleaned = clean_props({
        "name": "P-101A",
        "downtime": None,                              # dropped
        "ratings": ["7.5 kW", "2900 rpm"],             # flat list kept
        "series": [{"x": "1", "y": "2"}],              # nested -> json string
        "embedding": [0.1, 0.2],
    })

    assert "downtime" not in cleaned
    assert cleaned["ratings"] == ["7.5 kW", "2900 rpm"]
    assert isinstance(cleaned["series"], str) and '"x"' in cleaned["series"]
    assert cleaned["embedding"] == [0.1, 0.2]


def test_chart_like_subgraph_groups_with_safe_props():
    csg = make_subgraph()
    csg.nodes[0].props = {"series": [{"x": "2026-02-20", "y": "128"}],
                          "title": "trend"}

    batch = group_batch([csg])

    row = batch.nodes_by_label["Equipment"][0]
    assert isinstance(row["props"]["series"], str)     # would crash neo4j raw


def test_prov_hash_distinguishes_sources():
    p1 = Provenance(doc_id="d1", page=1, extractor_version="v1", confidence=0.9)
    p2 = Provenance(doc_id="d1", page=2, extractor_version="v1", confidence=0.9)

    assert prov_hash(p1) == prov_hash(p1)
    assert prov_hash(p1) != prov_hash(p2)
    # confidence is not part of identity, only of payload
    p3 = Provenance(doc_id="d1", page=1, extractor_version="v1", confidence=0.4)
    assert prov_hash(p1) == prov_hash(p3)
