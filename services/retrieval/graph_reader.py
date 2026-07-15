"""Every Cypher read in the service lives here, mirroring how graphd's
store.py owns every write. Edge types are string-formatted into patterns
(cypher can't parameterise them), so they are validated against the schema
enums first - same injection gate as the writer."""

from neo4j import GraphDatabase

from plantmind_core.config import get_settings
from plantmind_core.schemas import EdgeType

from retrieval.models import Path, Step

VALID_EDGE_TYPES = {t.value for t in EdgeType}


def _edge_pattern(types) -> str:
    bad = set(types) - VALID_EDGE_TYPES
    if bad:
        raise ValueError(f"unknown edge types: {bad}")
    return "|".join(types)


class GraphReader:
    def __init__(self, driver):
        self._driver = driver

    @classmethod
    def from_settings(cls) -> "GraphReader":
        s = get_settings()
        return cls(GraphDatabase.driver(
            s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password)))

    # ------------------------------------------------------------- linking
    def entity_by_surface(self, surface: str):
        records = self._run(
            "MATCH (e:Entity) WHERE e.surface_form = $surface "
            "AND NOT e:Chunk AND NOT e:Section AND NOT e:Document "
            "RETURN e.id AS id, e.surface_form AS surface, "
            "[l IN labels(e) WHERE l <> 'Entity'][0] AS label LIMIT 1",
            surface=surface)
        return records[0] if records else None

    def entities_by_name(self, phrase: str, limit=3):
        return self._run(
            "MATCH (e:Entity) WHERE toLower(e.surface_form) CONTAINS $phrase "
            "AND NOT e:Chunk AND NOT e:Section AND NOT e:Document "
            "RETURN e.id AS id, e.surface_form AS surface, "
            "[l IN labels(e) WHERE l <> 'Entity'][0] AS label LIMIT $limit",
            phrase=phrase.lower(), limit=limit)

    # ------------------------------------------------------------- chunks
    def vector_chunks(self, embedding: list, k: int = 8):
        return self._run(
            "CALL db.index.vector.queryNodes('chunk_embedding', $k, $embedding) "
            "YIELD node, score "
            "RETURN node.id AS id, node.text AS text, node.context AS context, "
            "node.page AS page, score ORDER BY score DESC",
            k=k, embedding=embedding)

    def chunks_containing(self, needle: str, limit: int = 6):
        return self._run(
            "MATCH (c:Chunk) WHERE c.text CONTAINS $needle "
            "RETURN c.id AS id, c.text AS text, c.context AS context, "
            "c.page AS page LIMIT $limit",
            needle=needle, limit=limit)

    def chunks_of_doc(self, doc_id: str):
        return self._run(
            "MATCH (c:Chunk) WHERE c.id STARTS WITH $prefix "
            "RETURN c.id AS id, c.text AS text, c.context AS context, "
            "c.page AS page, c.start AS start, c.end AS end",
            prefix=f"chunk:{doc_id}#")

    # ----------------------------------------------------------- local mode
    def relations_of(self, node_id: str, types, limit=40):
        pattern = _edge_pattern(types)
        return self._run(
            f"MATCH (n:Entity {{id: $id}})-[r:{pattern}]-(m:Entity) "
            "RETURN type(r) AS type, startNode(r).id AS src, "
            "endNode(r).id AS dst, properties(r) AS props, "
            "m.id AS other_id, m.surface_form AS other_surface, "
            "[l IN labels(m) WHERE l <> 'Entity'][0] AS other_label "
            "LIMIT $limit",
            id=node_id, limit=limit)

    # ------------------------------------------------------------ path mode
    def paths_between(self, src_id, dst_id, types, max_hops, limit=100):
        pattern = _edge_pattern(types)
        records = self._session_paths(
            f"MATCH p = (a:Entity {{id: $src}})-[:{pattern}*1..{max_hops}]-"
            f"(b:Entity {{id: $dst}}) RETURN p LIMIT $limit",
            src=src_id, dst=dst_id, limit=limit)
        return records

    def paths_outward(self, src_id, target_labels, types, max_hops, limit=100):
        pattern = _edge_pattern(types)
        label_filter = " OR ".join(f"b:{l}" for l in target_labels)
        return self._session_paths(
            f"MATCH p = (a:Entity {{id: $src}})-[:{pattern}*1..{max_hops}]-(b) "
            f"WHERE {label_filter} RETURN p LIMIT $limit",
            src=src_id, limit=limit)

    def out_degrees(self, node_ids, types) -> dict:
        pattern = _edge_pattern(types)
        records = self._run(
            f"UNWIND $ids AS nid MATCH (n:Entity {{id: nid}})-[r:{pattern}]-() "
            "RETURN nid AS id, count(r) AS degree",
            ids=list(node_ids))
        return {r["id"]: r["degree"] for r in records}

    # -------------------------------------------------------------- plumbing
    def _run(self, query, **params) -> list:
        with self._driver.session() as session:
            return [dict(r) for r in session.run(query, **params)]

    def _session_paths(self, query, **params) -> list:
        paths = []
        with self._driver.session() as session:
            for record in session.run(query, **params):
                p = record["p"]
                nodes = {n["id"]: {
                    "surface": n.get("surface_form", n["id"]),
                    "label": next((l for l in n.labels if l != "Entity"),
                                  "Entity"),
                } for n in p.nodes}
                steps = [Step(type=r.type, src=r.start_node["id"],
                              dst=r.end_node["id"], props=dict(r))
                         for r in p.relationships]
                paths.append(Path(nodes=nodes, steps=steps))
        return paths

    def close(self):
        self._driver.close()
