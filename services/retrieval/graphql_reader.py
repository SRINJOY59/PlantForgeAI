"""Adapter that reuses existing GraphReader methods for the GraphQL resolvers.

The GraphQL schema needs shapes like 'equipment with its failures, connections,
documents, and regulations'.  GraphReader already knows all those Cypher queries
individually; this module composes them into the richer objects the schema needs
without duplicating a single query string.
"""

from plantmind_core.config import get_settings
from plantmind_core.schemas import EdgeType

from retrieval.graph_reader import GraphReader, HEAVY_PROPS, VALID_EDGE_TYPES

# Edge types used for the 'connections' resolver on Equipment
_TOPO_EDGES = [t.value for t in EdgeType
               if t in (EdgeType.CONNECTED_TO, EdgeType.PART_OF,
                         EdgeType.FEEDS, EdgeType.SHARES_HEADER)]


class GraphQLReader:
    """Thin facade over GraphReader for the GraphQL resolvers."""

    def __init__(self, graph_reader: GraphReader):
        self._gr = graph_reader

    @classmethod
    def from_settings(cls) -> "GraphQLReader":
        return cls(GraphReader.from_settings())

    # ---------------------------------------------------------- top-level queries

    def plant_graph(self, limit: int = 400) -> dict:
        return self._gr.graph_snapshot(limit)

    def search_entities(self, phrase: str, limit: int = 10) -> list[dict]:
        return self._gr.entities_by_name(phrase, limit)

    def all_documents(self) -> list[dict]:
        return self._gr.documents()

    def equipment_by_tag(self, tag: str) -> dict | None:
        return self._gr.entity_by_surface(tag)

    # ---------------------------------------------------------- equipment detail

    def equipment_failures(self, tag: str) -> list[dict]:
        """Failure modes for one equipment tag."""
        node_id = self._resolve_id(tag)
        if not node_id:
            return []
        return self._gr._run(
            "MATCH (e:Equipment {id: $id})-[h:HAS_FAILURE]->(f:FailureMode) "
            "RETURN f.surface_form AS mode, count(h) AS count, "
            "[c IN collect(DISTINCT h.cause) WHERE c <> ''] AS causes, "
            "collect(DISTINCT h.doc_id) AS docs",
            id=node_id)

    def equipment_connections(self, tag: str) -> list[dict]:
        """Directly connected equipment/instruments."""
        return self._gr._run(
            "MATCH (e:Equipment {surface_form: $tag})-[:CONNECTED_TO]-(m:Entity) "
            "WHERE NOT m:Chunk AND NOT m:Section "
            "RETURN m.id AS id, m.surface_form AS surface, "
            "[l IN labels(m) WHERE l <> 'Entity'][0] AS label",
            tag=tag)

    def equipment_documents(self, tag: str) -> list[dict]:
        """Documents mentioning this equipment."""
        node_id = self._resolve_id(tag)
        if not node_id:
            return []
        return self._gr._run(
            "MATCH (e:Entity {id: $id})-[:MENTIONED_IN]->(d:Entity) "
            "WHERE d:Document OR d:Procedure OR d:WorkOrder "
            "RETURN d.id AS id, "
            "coalesce(d.filename, d.surface_form) AS filename, "
            "[l IN labels(d) WHERE l <> 'Entity'][0] AS label",
            id=node_id)

    def equipment_regulations(self, tag: str) -> list[dict]:
        """Governing regulatory clauses for this equipment."""
        node_id = self._resolve_id(tag)
        if not node_id:
            return []
        return self._gr._run(
            "MATCH (e:Entity {id: $id})-[g:GOVERNED_BY]->(r:RegulationClause) "
            "RETURN r.surface_form AS clause, g.revision AS revision, "
            "g.inspection_type AS inspection_type, g.next_due AS next_due, "
            "g.date AS last_inspection, g.doc_id AS doc_id",
            id=node_id)

    def equipment_work_orders(self, tag: str, limit: int = 10) -> list[dict]:
        """Recent work orders for this equipment."""
        return self._gr._run(
            "MATCH (e:Equipment {surface_form: $tag})-[:MENTIONED_IN]->(w:WorkOrder) "
            "RETURN w.surface_form AS wo_id, w.date AS date, "
            "w.description AS description, w.action_taken AS action_taken "
            "ORDER BY w.date DESC LIMIT $limit",
            tag=tag, limit=limit)

    def equipment_procedures(self, tag: str) -> list[dict]:
        """Fix procedures for this equipment."""
        return self._gr._run(
            "MATCH (e:Equipment {surface_form: $tag})-[:FIXED_BY]->(p:Procedure) "
            "RETURN p.surface_form AS procedure, "
            "collect(DISTINCT p.doc_id) AS docs",
            tag=tag)

    def inspection_schedule(self) -> list[dict]:
        """Every statutory obligation with a due date."""
        return self._gr._run(
            "MATCH (e:Entity)-[g:GOVERNED_BY]->(r:RegulationClause) "
            "WHERE g.next_due IS NOT NULL AND g.next_due <> '' "
            "RETURN e.surface_form AS equipment, "
            "r.surface_form AS standard, "
            "g.inspection_type AS inspection_type, "
            "g.next_due AS next_due, g.date AS last_inspection, "
            "g.revision AS revision, g.doc_id AS doc_id "
            "ORDER BY g.next_due")

    # ---------------------------------------------------------- helpers

    def _resolve_id(self, tag: str) -> str | None:
        """Surface form → node id."""
        rec = self._gr.entity_by_surface(tag)
        return rec["id"] if rec else None

    def close(self):
        self._gr.close()
