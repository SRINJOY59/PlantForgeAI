"""The graph side of the memory layer: FaultModes as they live in Neo4j.

A FaultSignature is the statistical world's output - a bag of numbers with no
opinion about equipment or procedures. A FaultMode is that fingerprint hung in
the graph next to the assets it touches and the SOP that answers it, so the
agent can cite a matched fault exactly as it cites a document. This store is the
one place that translation happens; it holds the Cypher and nothing else knows
the node shape.

The signature travels as a JSON string on the node. Neo4j properties are flat -
no nested lists of maps - and the alternative (exploding every TagDeviation into
its own node and edge) would bury the one thing a FaultMode is for (being read
back whole and compared) under a graph walk. The flat columns we do keep
(deviation_tags, lead_tag) exist only so the graph can filter candidates cheaply
before the matcher rehydrates the full signature and scores it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from neo4j import GraphDatabase

from plantmind_core.config import get_settings
from plantmind_core.schemas import FaultMode, FaultSignature, NodeType, EdgeType
from plantmind_core.telemetry import get_logger

log = get_logger("diagnostics.library")

_FAULT_MODE = NodeType.FAULT_MODE.value
_EXHIBITS = EdgeType.EXHIBITS_FAULT.value
_RESPONDS = EdgeType.RESPONDS_WITH.value


class FaultLibraryStore:
    """Write and read the learned fault library in Neo4j."""

    def __init__(self, driver):
        self._driver = driver

    @classmethod
    def from_settings(cls) -> "FaultLibraryStore":
        s = get_settings()
        driver = GraphDatabase.driver(
            s.neo4j_uri,
            auth=(s.neo4j_user, s.neo4j_password),
            max_connection_pool_size=20,
            connection_acquisition_timeout=30.0,
            max_transaction_retry_time=15.0,
        )
        return cls(driver)

    # writes ----------------------------------------------------------------
    def store(self, fm: FaultMode) -> None:
        """MERGE one FaultMode and its edges. Idempotent: re-running a campaign
        overwrites the fingerprint in place rather than duplicating it, so the
        library converges instead of growing a new node per run."""
        with self._driver.session() as session:
            session.execute_write(self._store_tx, fm)
        log.info("fault mode stored", id=fm.id, cause=fm.cause_id,
                 areas=len(fm.unit_areas),
                 deviations=len(fm.signature.deviations))

    @staticmethod
    def _store_tx(tx, fm: FaultMode) -> None:
        sig = fm.signature
        lead = sig.deviations[0].tag_id if sig.deviations else ""
        props = {
            "id": fm.id,
            "cause_id": fm.cause_id or "",
            "cause_label": fm.cause_label,
            "source": sig.source,
            "severity": sig.severity,
            "window_s": sig.window_s,
            "signature_json": sig.model_dump_json(),
            "deviation_tags": [d.tag_id for d in sig.deviations],
            "lead_tag": lead,
            "unit_areas": fm.unit_areas,
        }
        # the FaultMode node itself. :Entity base label matches every other node
        # in the graph, so the existing readers' (e:Entity {id}) matches find it.
        tx.run(
            f"MERGE (f:Entity {{id: $id}}) "
            f"SET f:{_FAULT_MODE}, f += $props, f.plant = 'TEP', "
            f"    f.updated_at = $updated_at",
            id=fm.id, props=props,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        # equipment -> fault. Only links areas that already exist as Equipment
        # (seeded topology); a MATCH that misses simply makes no edge, so an
        # unknown area never invents a node.
        for area in fm.unit_areas:
            tx.run(
                f"MATCH (e:Equipment {{surface_form: $area}}) "
                f"MATCH (f:{_FAULT_MODE} {{id: $id}}) "
                f"MERGE (e)-[r:{_EXHIBITS}]->(f) "
                f"SET r.source = $source",
                area=area, id=fm.id, source=sig.source,
            )
        # fault -> procedure, when one is linked and present in the graph
        if fm.procedure_id:
            tx.run(
                f"MATCH (f:{_FAULT_MODE} {{id: $id}}) "
                f"MATCH (p:Procedure {{id: $pid}}) "
                f"MERGE (f)-[:{_RESPONDS}]->(p)",
                id=fm.id, pid=fm.procedure_id,
            )

    # reads -----------------------------------------------------------------
    def all(self) -> list[FaultMode]:
        """Every stored FaultMode, rehydrated. The Library view's whole dataset,
        and the corpus the matcher scores a live signature against."""
        with self._driver.session() as session:
            rows = session.execute_read(self._all_tx)
        out: list[FaultMode] = []
        for r in rows:
            fm = self._row_to_fault_mode(r)
            if fm is not None:
                out.append(fm)
        return out

    @staticmethod
    def _all_tx(tx) -> list[dict]:
        result = tx.run(
            f"MATCH (f:{_FAULT_MODE}) "
            f"OPTIONAL MATCH (f)-[:{_RESPONDS}]->(p:Procedure) "
            f"RETURN f.id AS id, f.cause_id AS cause_id, "
            f"       f.cause_label AS cause_label, f.unit_areas AS unit_areas, "
            f"       f.signature_json AS signature_json, "
            f"       p.id AS procedure_id "
            f"ORDER BY f.cause_id"
        )
        return [dict(rec) for rec in result]

    @staticmethod
    def _row_to_fault_mode(r: dict) -> "FaultMode | None":
        raw = r.get("signature_json")
        if not raw:
            log.warning("fault mode missing signature", id=r.get("id"))
            return None
        try:
            sig = FaultSignature.model_validate_json(raw)
        except Exception as e:                       # a hand-edited node, say
            log.warning("fault mode signature unreadable",
                        id=r.get("id"), error=str(e)[:120])
            return None
        return FaultMode(
            id=r["id"],
            cause_id=r.get("cause_id") or None,
            cause_label=r.get("cause_label") or "",
            unit_areas=r.get("unit_areas") or [],
            signature=sig,
            procedure_id=r.get("procedure_id"),
        )

    def close(self) -> None:
        self._driver.close()
