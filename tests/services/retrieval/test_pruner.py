from retrieval.pruner import FlowPruner
from conftest import make_path


def pruner(top_k=5):
    return FlowPruner(alpha=0.8, top_k=top_k)


def test_shorter_paths_score_higher():
    short = make_path(("A", "CONNECTED_TO", "B"))
    long = make_path(("A", "CONNECTED_TO", "X"), ("X", "CONNECTED_TO", "Y"),
                     ("Y", "CONNECTED_TO", "B"))

    degrees = {n: 2 for n in ("A", "B", "X", "Y")}
    p = pruner()
    assert p.score(short, degrees) > p.score(long, degrees)


def test_paths_through_hubs_are_diluted():
    via_specific = make_path(("A", "CONNECTED_TO", "M"), ("M", "CONNECTED_TO", "B"))
    via_hub = make_path(("A", "CONNECTED_TO", "H"), ("H", "CONNECTED_TO", "B"))

    degrees = {"A": 2, "B": 2, "M": 2, "H": 30}   # H touches everything
    p = pruner()
    assert p.score(via_specific, degrees) > p.score(via_hub, degrees)


def test_confidence_weights_the_flow():
    confident = make_path(("A", "HAS_FAILURE", "B"), confidence=1.0)
    hedged = make_path(("A", "HAS_FAILURE", "B"), confidence=0.6)

    degrees = {"A": 2, "B": 2}
    p = pruner()
    assert p.score(confident, degrees) > p.score(hedged, degrees)


def test_low_confidence_weakens_but_never_erases():
    path = make_path(("A", "HAS_FAILURE", "B"), confidence=0.0)
    assert pruner().score(path, {"A": 2, "B": 2}) > 0


def test_prune_keeps_best_and_drops_near_duplicates():
    best = make_path(("A", "CONNECTED_TO", "B"))
    duplicate = make_path(("A", "CONNECTED_TO", "B"))          # same edge
    different = make_path(("A", "GOVERNED_BY", "R"))

    kept = pruner().prune([duplicate, best, different], {})

    assert len(kept) == 2
    assert kept[0].score >= kept[1].score
    edge_types = {s.type for p in kept for s in p.steps}
    assert edge_types == {"CONNECTED_TO", "GOVERNED_BY"}


def test_prune_respects_top_k():
    paths = [make_path((f"A{i}", "CONNECTED_TO", f"B{i}")) for i in range(10)]
    assert len(pruner(top_k=3).prune(paths, {})) == 3


def test_undirected_edge_identity():
    forward = make_path(("A", "CONNECTED_TO", "B"))
    backward = make_path(("B", "CONNECTED_TO", "A"))
    assert forward.edge_keys() == backward.edge_keys()
