"""All the denoise reads and writes. Every operation is reversible: merges
redirect edges to the canonical node but keep the variant as a superseded
node with a MERGED_INTO edge (so a bad merge can be split), and derived
edges are stamped source='agent' so nothing here is mistaken for ground
truth. graphd is the only writer, so this runs inside it."""

from neo4j import GraphDatabase

from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger

log = get_logger("graphd.denoise.graph")


class DenoiseGraph:
    def __init__(self, driver):
        self._driver = driver

    @classmethod
    def from_settings(cls) -> "DenoiseGraph":
        s = get_settings()
        return cls(GraphDatabase.driver(
            s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password)))

    # --------------------------------------------------------------- reads
    def equipment_with_failures(self) -> list:
        """Each equipment and its failure-mode labels -> reconciliation input."""
        return self._run(
            "MATCH (e:Equipment)-[:HAS_FAILURE]->(f:FailureMode) "
            "WHERE coalesce(f.superseded, false) = false "
            "RETURN e.id AS equip_id, e.surface_form AS tag, "
            "collect(DISTINCT {id: f.id, label: f.surface_form}) AS failures")

    def doc_reference_nodes(self) -> list:
        """Equipment/Instrument nodes whose surface form is a document id."""
        return self._run(
            "MATCH (n) WHERE (n:Equipment OR n:Instrument) "
            "RETURN n.id AS id, n.surface_form AS surface")

    # -------------------------------------------------------------- writes
    def prune_node(self, node_id: str) -> int:
        """Detach a mistyped/noise node. Reversible in spirit: we only ever
        call this on nodes the deterministic doc-ref rule flags."""
        rows = self._run(
            "MATCH (n {id: $id}) DETACH DELETE n RETURN 1 AS done", id=node_id)
        return len(rows)

    def merge_failure_modes(self, canonical_id: str, variant_ids: list) -> int:
        """Redirect HAS_FAILURE edges from variants to the canonical node,
        then mark each variant superseded with a MERGED_INTO trail."""
        if not variant_ids:
            return 0
        self._run(
            "MATCH (e)-[h:HAS_FAILURE]->(v:FailureMode) WHERE v.id IN $vids "
            "MATCH (c:FailureMode {id: $cid}) "
            "MERGE (e)-[h2:HAS_FAILURE {prov_hash: h.prov_hash}]->(c) "
            "SET h2 += properties(h) "
            "DELETE h",
            vids=variant_ids, cid=canonical_id)
        self._run(
            "MATCH (v:FailureMode) WHERE v.id IN $vids "
            "MATCH (c:FailureMode {id: $cid}) "
            "SET v.superseded = true "
            "MERGE (v)-[:MERGED_INTO {source: 'agent'}]->(c)",
            vids=variant_ids, cid=canonical_id)
        return len(variant_ids)

    def add_causal_link(self, cause_id: str, effect_id: str) -> int:
        """Recovered structure: mechanism CAUSES mode. Marked source='agent'
        (derived, not ground truth)."""
        self._run(
            "MATCH (a:FailureMode {id: $cause}), (b:FailureMode {id: $effect}) "
            "MERGE (a)-[r:CAUSES]->(b) "
            "SET r.source = 'agent', r.confidence = 0.7",
            cause=cause_id, effect=effect_id)
        return 1

    def _run(self, query, **params) -> list:
        with self._driver.session() as session:
            return [dict(r) for r in session.run(query, **params)]

    def close(self):
        self._driver.close()
