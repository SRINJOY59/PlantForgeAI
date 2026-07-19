from neo4j import GraphDatabase

from plantmind_core.config import get_settings
from plantmind_core.schemas import EdgeType, NodeType
from plantmind_core.telemetry import get_logger

from graphd.batching import WriteBatch

log = get_logger("graphd.store")

# labels/types are string-formatted into cypher (they can't be parameterised),
# so they must come from the schema enums and nowhere else
VALID_LABELS = {t.value for t in NodeType}
VALID_EDGE_TYPES = {t.value for t in EdgeType}


class GraphStore:
    def __init__(self, driver):
        self._driver = driver

    @classmethod
    def from_settings(cls) -> "GraphStore":
        s = get_settings()
        driver = GraphDatabase.driver(
            s.neo4j_uri,
            auth=(s.neo4j_user, s.neo4j_password),
            max_connection_pool_size=50,
            connection_acquisition_timeout=30.0,
            max_transaction_retry_time=15.0,
        )
        return cls(driver)

    def write_batch(self, batch: WriteBatch, version: int) -> None:
        bad_labels = set(batch.nodes_by_label) - VALID_LABELS
        bad_edges = set(batch.edges_by_type) - VALID_EDGE_TYPES
        if bad_labels or bad_edges:
            raise ValueError(f"unknown labels {bad_labels} or edge types {bad_edges}")

        with self._driver.session() as session:
            session.execute_write(self._write_tx, batch, version)
        log.info("batch committed", version=version,
                 nodes=len(batch.node_ids),
                 edges=sum(len(r) for r in batch.edges_by_type.values()))

    @staticmethod
    def _write_tx(tx, batch: WriteBatch, version: int):
        for label, rows in batch.nodes_by_label.items():
            tx.run(
                f"UNWIND $rows AS row "
                f"MERGE (n:Entity {{id: row.id}}) "
                f"ON CREATE SET n.created_version = $version "
                f"SET n:{label}, n += row.props, n.updated_version = $version",
                rows=rows, version=version,
            )
        for edge_type, rows in batch.edges_by_type.items():
            tx.run(
                f"UNWIND $rows AS row "
                f"MATCH (a:Entity {{id: row.src}}) "
                f"MATCH (b:Entity {{id: row.dst}}) "
                f"MERGE (a)-[r:{edge_type} {{prov_hash: row.prov_hash}}]->(b) "
                f"SET r += row.props, r.updated_version = $version",
                rows=rows, version=version,
            )

    def close(self) -> None:
        self._driver.close()
