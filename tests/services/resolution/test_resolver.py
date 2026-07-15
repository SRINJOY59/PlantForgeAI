import fakeredis

from plantmind_core import keys
from plantmind_core.bus import RedisBus
from plantmind_core.schemas import (
    CandidateEdge, CandidateNode, CandidateSubgraph, EdgeType, NodeType, Provenance,
)

from resolution.resolver import Resolver
from resolution.service import ResolutionService


def run_resolve(payload, bus, resolver):
    """Service resolves (pure); the adapter's bus push is emulated here."""
    csg = ResolutionService(resolver).resolve(payload)
    bus.queue_subgraph(csg.model_dump_json())
    return {"status": "queued_for_write", "doc_id": csg.doc_id,
            "nodes": len(csg.nodes)}


def csg_with(nodes):
    return CandidateSubgraph(doc_id="d1", content_hash="h1", nodes=nodes,
                             edges=[])


def test_same_tag_any_spelling_resolves_to_one_id():
    r = Resolver()
    assert r.canonical(NodeType.EQUIPMENT, "P-101A") == "equip:P-101A"
    assert r.canonical(NodeType.EQUIPMENT, "p 101 a") == "equip:P-101A"
    assert r.canonical(NodeType.EQUIPMENT, "P101A") == "equip:P-101A"


def test_types_get_distinct_namespaces():
    r = Resolver()
    assert r.canonical(NodeType.INSTRUMENT, "PI-102") == "inst:PI-102"
    assert r.canonical(NodeType.WORK_ORDER, "wo-2214") == "wo:WO-2214"
    assert r.canonical(NodeType.FAILURE_MODE, "SEAL LEAK") == "fm:seal-leak"
    assert r.canonical(NodeType.PROCEDURE,
                       "Mechanical Seal Replacement") == \
        "proc:mechanical-seal-replacement"
    assert r.canonical(NodeType.REGULATION_CLAUSE,
                       "OISD-STD-128") == "reg:oisd-std-128"


def test_doc_scoped_nodes_keep_their_surface():
    r = Resolver()
    assert r.canonical(NodeType.CHUNK, "abc123#chunk4") == "chunk:abc123#chunk4"
    assert r.canonical(NodeType.SECTION, "abc123#sec1") == "sec:abc123#sec1"


def test_resolve_stamps_every_node():
    csg = csg_with([
        CandidateNode(type=NodeType.EQUIPMENT, surface_form="P-101A"),
        CandidateNode(type=NodeType.FAILURE_MODE, surface_form="SEAL-LEAK"),
        CandidateNode(type=NodeType.DOCUMENT, surface_form="d1"),
    ])

    resolved = Resolver().resolve(csg)

    assert all(n.resolved_id for n in resolved.nodes)
    assert resolved.nodes[0].resolved_id == "equip:P-101A"


def test_run_resolve_queues_writable_subgraph():
    bus = RedisBus(fakeredis.FakeRedis(decode_responses=True))
    csg = CandidateSubgraph(
        doc_id="d1", content_hash="h1",
        nodes=[CandidateNode(type=NodeType.EQUIPMENT, surface_form="P-101A"),
               CandidateNode(type=NodeType.DOCUMENT, surface_form="d1")],
        edges=[CandidateEdge(type=EdgeType.MENTIONED_IN, src="P-101A", dst="d1",
                             provenance=Provenance(doc_id="d1",
                                                   extractor_version="v1",
                                                   confidence=1.0))])

    result = run_resolve(csg.model_dump(mode="json"), bus, Resolver())

    assert result["status"] == "queued_for_write"
    (queued,) = bus.take_subgraphs(10)
    shipped = CandidateSubgraph.model_validate_json(queued)
    assert shipped.nodes[0].resolved_id == "equip:P-101A"

    # and what we queued is exactly what graphd's batcher needs
    from graphd.batching import group_batch
    batch = group_batch([shipped])
    assert "equip:P-101A" in batch.node_ids
