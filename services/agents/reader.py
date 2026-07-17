"""The graph reads the agents need. Kept separate from retrieval's reader
so the two services stay independent; the few queries here are the agents'
own concern (sibling failures, overdue compliance)."""

from neo4j import GraphDatabase

from plantmind_core.config import get_settings


class AgentReader:
    def __init__(self, driver):
        self._driver = driver

    @classmethod
    def from_settings(cls) -> "AgentReader":
        s = get_settings()
        return cls(GraphDatabase.driver(
            s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password)))

    def equipment_failures(self, node_id: str) -> list:
        """Failure modes on one equipment node, with occurrence counts."""
        return self._run(
            "MATCH (e:Equipment {id: $id})-[h:HAS_FAILURE]->(f:FailureMode) "
            "RETURN e.surface_form AS tag, f.surface_form AS mode, "
            "count(h) AS count, "
            "[c IN collect(DISTINCT h.cause) WHERE c <> ''] AS causes, "
            "collect(DISTINCT h.doc_id) AS docs",
            id=node_id)

    def family_history(self, family: str, mode: str, exclude_tag: str) -> list:
        """Sibling equipment (tag sharing the family stem, e.g. 'P-101')
        that suffered the same failure mode - the basis of a pattern alert."""
        return self._run(
            "MATCH (e:Equipment)-[h:HAS_FAILURE]->(f:FailureMode {surface_form: $mode}) "
            "WHERE e.surface_form STARTS WITH $family "
            "AND e.surface_form <> $exclude "
            "RETURN e.surface_form AS tag, count(h) AS count, "
            "[c IN collect(DISTINCT h.cause) WHERE c <> ''] AS causes, "
            "collect(DISTINCT h.doc_id) AS docs",
            family=family, mode=mode, exclude=exclude_tag)

    def procedures_for(self, tag: str) -> list:
        """Procedures that fix a piece of equipment - what to actually do."""
        return self._run(
            "MATCH (e:Equipment {surface_form: $tag})-[x:FIXED_BY]->(p:Procedure) "
            "RETURN p.surface_form AS procedure, "
            "collect(DISTINCT x.doc_id) AS docs",
            tag=tag)

    def connected_equipment(self, tag: str) -> list:
        """Directly connected equipment/instruments - the process context."""
        return self._run(
            "MATCH (e:Equipment {surface_form: $tag})-[:CONNECTED_TO]-(m:Entity) "
            "RETURN m.surface_form AS tag, "
            "[l IN labels(m) WHERE l <> 'Entity'][0] AS label",
            tag=tag)

    def work_orders_for(self, tag: str, limit=10) -> list:
        """Recent work-order history with actions taken."""
        return self._run(
            "MATCH (e:Equipment {surface_form: $tag})-[:MENTIONED_IN]->(w:WorkOrder) "
            "RETURN w.surface_form AS wo_id, w.date AS date, "
            "w.description AS description, w.action_taken AS action_taken "
            "ORDER BY w.date DESC LIMIT $limit",
            tag=tag, limit=limit)

    def governing_standards(self) -> list:
        """Every standard the plant is actually held to, and what it holds.

        This is the whole point of watching revisions here rather than
        subscribing to a newsletter: a newsletter says OISD-STD-129 changed,
        this says which fourteen vessels that lands on and when each was last
        inspected against it.
        """
        return self._run(
            "MATCH (e:Entity)-[g:GOVERNED_BY]->(r:RegulationClause) "
            "RETURN r.surface_form AS standard, "
            "collect(DISTINCT e.surface_form) AS equipment, "
            "count(DISTINCT e) AS affected, "
            "max(g.date) AS last_inspection, "
            "[d IN collect(DISTINCT g.doc_id) WHERE d IS NOT NULL] AS docs "
            "ORDER BY affected DESC")

    def overdue_inspections(self, today: str) -> list:
        return self._run(
            "MATCH (e:Entity)-[g:GOVERNED_BY]->(r:RegulationClause) "
            "WHERE g.next_due < $today AND g.next_due <> '' "
            "RETURN e.surface_form AS equipment, r.surface_form AS standard, "
            "g.inspection_type AS inspection_type, g.next_due AS next_due, "
            "g.doc_id AS doc_id, g.page AS page ORDER BY g.next_due",
            today=today)

    def _run(self, query, **params) -> list:
        with self._driver.session() as session:
            return [dict(r) for r in session.run(query, **params)]

    def close(self):
        self._driver.close()
