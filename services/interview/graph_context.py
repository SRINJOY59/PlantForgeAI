"""The read-only graph looks the interviewer needs: what equipment lives in
the retiree's corner of the plant and what already went wrong with it. Kept
separate from the agents' and retrieval's readers so the services stay
independent; every query degrades to [] when Neo4j is down or empty, because
an interview grounded only in the profile is still worth running."""

from neo4j import GraphDatabase

from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger

log = get_logger("interview.graph")


class InterviewGraphReader:
    def __init__(self, driver):
        self._driver = driver

    @classmethod
    def from_settings(cls) -> "InterviewGraphReader":
        s = get_settings()
        return cls(GraphDatabase.driver(
            s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password)))

    def equipment_matching(self, terms: list, limit: int = 20) -> list:
        """Equipment whose tag or name matches any of the profile-derived
        terms (unit names, project keywords, tag stems like 'P-101')."""
        if not terms:
            return []
        return self._run(
            "MATCH (e:Equipment) "
            "WHERE any(t IN $terms WHERE toLower(e.surface_form) CONTAINS toLower(t)) "
            "RETURN DISTINCT e.surface_form AS tag LIMIT $limit",
            terms=terms, limit=limit)

    def work_orders_for(self, tag: str, limit: int = 8) -> list:
        return self._run(
            "MATCH (e:Equipment {surface_form: $tag})-[:MENTIONED_IN]->(w:WorkOrder) "
            "RETURN w.surface_form AS wo_id, w.date AS date, "
            "w.description AS description, w.action_taken AS action_taken "
            "ORDER BY w.date DESC LIMIT $limit",
            tag=tag, limit=limit)

    def equipment_failures(self, tag: str) -> list:
        return self._run(
            "MATCH (e:Equipment {surface_form: $tag})-[h:HAS_FAILURE]->(f:FailureMode) "
            "RETURN f.surface_form AS mode, count(h) AS count, "
            "[c IN collect(DISTINCT h.cause) WHERE c <> ''] AS causes",
            tag=tag)

    def procedures_for(self, tag: str) -> list:
        return self._run(
            "MATCH (e:Equipment {surface_form: $tag})-[:FIXED_BY]->(p:Procedure) "
            "RETURN DISTINCT p.surface_form AS procedure",
            tag=tag)

    def connected_equipment(self, tag: str) -> list:
        return self._run(
            "MATCH (e:Equipment {surface_form: $tag})-[:CONNECTED_TO]-(m:Entity) "
            "RETURN DISTINCT m.surface_form AS tag",
            tag=tag)

    def person_docs(self, name: str, limit: int = 10) -> list:
        """Documents the graph already links to this person - what the plant
        has on record about them, so the agent asks past it, not about it."""
        if not name:
            return []
        return self._run(
            "MATCH (p:Person)-[:MENTIONED_IN]->(d:Document) "
            "WHERE toLower(p.surface_form) CONTAINS toLower($name) "
            "RETURN DISTINCT coalesce(d.surface_form, d.doc_number, d.id) AS doc "
            "LIMIT $limit",
            name=name, limit=limit)

    def _run(self, query, **params) -> list:
        try:
            with self._driver.session() as session:
                return [dict(r) for r in session.run(query, **params)]
        except Exception as e:
            log.warning("graph read failed", error=str(e)[:200])
            return []

    def close(self):
        try:
            self._driver.close()
        except Exception:
            pass
