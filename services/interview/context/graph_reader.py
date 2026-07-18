"""The read-only graph looks the interviewer needs: what equipment lives in
the retiree's corner of the plant and what already went wrong with it. Kept
separate from the agents' and retrieval's readers so the services stay
independent; every query degrades to [] when Neo4j is down or empty, because
an interview grounded only in the profile is still worth running."""

from neo4j import GraphDatabase

from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger

log = get_logger("interview.context.graph")


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

    def equipment_context(self, tags: list) -> dict:
        """Everything the brief needs about a set of equipment, in ONE query
        instead of four per tag. Pattern comprehensions pull each tag's
        failures, work orders, procedures and connections in a single round
        trip; the grouping/sorting the per-tag queries used to do in Cypher is
        done here in Python over small in-memory lists.

        Returns {tag: {failures, work_orders, procedures, connected}}, with the
        same row shapes the four old methods produced, so the builder is
        unchanged below it.
        """
        if not tags:
            return {}
        rows = self._run(
            "UNWIND $tags AS tag "
            "MATCH (e:Equipment {surface_form: tag}) "
            "RETURN tag, "
            "[(e)-[h:HAS_FAILURE]->(f:FailureMode) | "
            "  {mode: f.surface_form, cause: coalesce(h.cause, '')}] AS failures, "
            "[(e)-[:MENTIONED_IN]->(w:WorkOrder) | "
            "  {wo_id: w.surface_form, date: w.date, "
            "   description: w.description, action_taken: w.action_taken}] "
            "  AS work_orders, "
            "[(e)-[:FIXED_BY]->(p:Procedure) | p.surface_form] AS procedures, "
            "[(e)-[:CONNECTED_TO]-(m:Entity) | m.surface_form] AS connected",
            tags=list(tags))
        return {r["tag"]: {
            "failures": self._group_failures(r["failures"]),
            "work_orders": self._recent(r["work_orders"]),
            "procedures": [{"procedure": p}
                           for p in dict.fromkeys(r["procedures"])],
            "connected": [{"tag": t} for t in dict.fromkeys(r["connected"])],
        } for r in rows}

    @staticmethod
    def _group_failures(rows: list) -> list:
        """[{mode, cause}] per HAS_FAILURE edge -> [{mode, count, causes}],
        matching what the old equipment_failures aggregate returned."""
        modes = {}
        for row in rows:
            entry = modes.setdefault(
                row["mode"], {"mode": row["mode"], "count": 0, "causes": []})
            entry["count"] += 1
            cause = (row.get("cause") or "").strip()
            if cause and cause not in entry["causes"]:
                entry["causes"].append(cause)
        return list(modes.values())

    @staticmethod
    def _recent(work_orders: list, limit: int = 8) -> list:
        return sorted(work_orders, key=lambda w: w.get("date") or "",
                      reverse=True)[:limit]

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
