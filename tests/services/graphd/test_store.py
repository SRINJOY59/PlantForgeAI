import pytest

from graphd.batching import group_batch
from graphd.store import GraphStore
from conftest import make_subgraph


class FakeTx:
    def __init__(self):
        self.queries = []

    def run(self, query, **params):
        self.queries.append((query, params))


class FakeSession:
    def __init__(self, tx):
        self.tx = tx

    def execute_write(self, fn, *args):
        return fn(self.tx, *args)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeDriver:
    def __init__(self):
        self.tx = FakeTx()

    def session(self):
        return FakeSession(self.tx)


def test_write_batch_issues_unwind_merges_keyed_on_entity_id():
    driver = FakeDriver()
    store = GraphStore(driver)
    batch = group_batch([make_subgraph()])

    store.write_batch(batch, version=7)

    queries = [q for q, _ in driver.tx.queries]
    node_queries = [q for q in queries if "MERGE (n:Entity {id: row.id})" in q]
    edge_queries = [q for q in queries if "MERGE (a)-[r:MENTIONED_IN" in q]
    assert len(node_queries) == 2  # Equipment + Document label groups
    assert len(edge_queries) == 1
    assert any("SET n:Equipment" in q for q in node_queries)

    for _, params in driver.tx.queries:
        assert params["version"] == 7
        assert isinstance(params["rows"], list)


def test_edge_merge_is_keyed_on_prov_hash():
    driver = FakeDriver()
    store = GraphStore(driver)
    batch = group_batch([make_subgraph()])

    store.write_batch(batch, version=1)

    edge_query, params = next(
        (q, p) for q, p in driver.tx.queries if "MENTIONED_IN" in q
    )
    assert "{prov_hash: row.prov_hash}" in edge_query
    assert params["rows"][0]["prov_hash"]


def test_unknown_label_rejected_before_touching_db():
    driver = FakeDriver()
    store = GraphStore(driver)
    batch = group_batch([make_subgraph()])
    batch.nodes_by_label["Turbine; DROP DATABASE"] = [{"id": "x", "props": {}}]

    with pytest.raises(ValueError, match="unknown labels"):
        store.write_batch(batch, version=1)
    assert driver.tx.queries == []
