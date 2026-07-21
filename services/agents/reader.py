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
            s.neo4j_uri,
            auth=(s.neo4j_user, s.neo4j_password),
            max_connection_pool_size=50,
            connection_acquisition_timeout=30.0,
            max_transaction_retry_time=15.0,
        ))

    def equipment_failures(self, node_id: str) -> list:
        """Failure modes on one equipment node, with occurrence counts, and
        any correction an engineer has made to the documents behind them.

        The correction rides along with the failure on purpose. An agent
        reasoning about this equipment has to see both the claim and its
        rebuttal, or it will confidently repeat a mistake somebody already
        caught. Behind a tool of its own, seeing it would be optional - which
        is the one thing it must not be.

        The join goes through the documents rather than the failure edge: a
        correction is filed against the sources an answer leaned on, so
        CORRECTED_BY hangs off the Document, never off HAS_FAILURE. Looking for
        it on the edge finds nothing, quietly, forever.

        count(DISTINCT h) because the OPTIONAL MATCH fans out - a failure whose
        source was corrected twice would otherwise report twice the failures.
        """
        return self._run(
            "MATCH (e:Equipment {id: $id})-[h:HAS_FAILURE]->(f:FailureMode) "
            "OPTIONAL MATCH (src:Document {surface_form: h.doc_id})"
            "-[:CORRECTED_BY]->(c:Document) "
            "RETURN e.surface_form AS tag, f.surface_form AS mode, "
            "count(DISTINCT h) AS count, "
            "[x IN collect(DISTINCT h.cause) WHERE x <> ''] AS causes, "
            "collect(DISTINCT h.doc_id) AS docs, "
            "collect(DISTINCT h.source) AS sources, "
            "[a IN collect(DISTINCT c.author) WHERE a IS NOT NULL] "
            "AS corrected_by, "
            "[t IN collect(DISTINCT c.text) WHERE t IS NOT NULL] "
            "AS corrections, "
            "[i IN collect(DISTINCT c.id) WHERE i IS NOT NULL] "
            "AS correction_ids",
            id=node_id)

    def governing_clauses(self, node_id: str) -> list:
        """What one piece of equipment is legally held to, and to which
        revision - the clauses a change to it would have to answer for."""
        return self._run(
            "MATCH (e:Entity {id: $id})-[g:GOVERNED_BY]->(r:RegulationClause) "
            "RETURN r.surface_form AS clause, g.revision AS revision, "
            "g.inspection_type AS inspection_type, g.next_due AS next_due, "
            "g.date AS last_inspection, g.doc_id AS doc_id",
            id=node_id)

    def documents_mentioning(self, node_id: str) -> list:
        """Documents and procedures that refer to this equipment.

        For a change assessment this is not background reading, it is a
        deliverable: every one of these is a document somebody has to revise
        before the change can close out.

        Named, not hashed. A Document's surface_form is its content hash, which
        is the right identity for the graph and useless to the engineer who has
        to go and edit the thing - "revise 6d6d71a9e053a1bd" is not a task
        anyone can act on. WorkOrders carry no filename because their
        surface_form is already the name a human uses, hence the coalesce.
        """
        return self._run(
            "MATCH (e:Entity {id: $id})-[m:MENTIONED_IN]->(d:Entity) "
            "WHERE d:Document OR d:Procedure OR d:WorkOrder "
            "RETURN coalesce(d.filename, d.surface_form) AS document, "
            "[l IN labels(d) WHERE l <> 'Entity'][0] AS label, "
            "d.kind AS kind, m.doc_id AS doc_id "
            "ORDER BY document",
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

    def document_names(self, doc_ids) -> dict:
        """{doc_id -> filename} for a set of documents, so a citation can show
        a name instead of a content hash. Missing filenames simply do not
        appear in the map, and the caller falls back to the id."""
        ids = list({d for d in doc_ids if d})
        if not ids:
            return {}
        # The OR looks like it would defeat the index, but it does not: given a
        # RANGE index on both Document.id and Document.surface_form, the cost
        # planner rewrites this into a Union of two NodeIndexSeeks by itself
        # (verified with EXPLAIN). Hand-unrolling it into UNION ALL produces the
        # same plan, so the readable form stays. It is the indexes that matter
        # here - without them this is a scan of every Document in the graph.
        rows = self._run(
            "MATCH (d:Document) WHERE d.id IN $ids OR d.surface_form IN $ids "
            "RETURN d.id AS id, d.surface_form AS sf, d.filename AS filename",
            ids=ids)
        names = {}
        for r in rows:
            if not r.get("filename"):
                continue
            # cited either by full id (doc:hash) or bare surface_form (hash)
            for key in (r["id"], r["sf"]):
                if key:
                    names[key] = r["filename"]
        return names

    def name_citations(self, citations) -> None:
        """Fill each citation's display name in place. An alert's sources are
        content hashes as built; this makes them readable and, once the doc_id
        is paired with a name, something the UI can open. Mutates, because an
        alert is passed around by reference on its way to the stream."""
        if not citations:
            return
        names = self.document_names({c.doc_id for c in citations})
        for c in citations:
            c.filename = names.get(c.doc_id) or names.get(f"doc:{c.doc_id}")

    def _run(self, query, **params) -> list:
        with self._driver.session() as session:
            return [dict(r) for r in session.run(query, **params)]

    def sop_steps(self, work_order_id: str) -> list:
        """Ordered SOP steps for a work order.

        Tries two paths:
        1. WorkOrder -[:FOLLOWS_SOP]-> Procedure  (direct link if extracted)
        2. WorkOrder mentions Equipment, Equipment -[:FIXED_BY]-> Procedure
           (the common case when WO and SOP were ingested separately)

        Returns rows with 'step_index', 'step_text', 'sop_id', 'sop_name'
        so the caller can cache the full list at session start.
        """
        # Path 1: direct SOP link
        direct = self._run(
            "MATCH (w:WorkOrder {surface_form: $wo_id})-[:FOLLOWS_SOP]->(p:Procedure) "
            "UNWIND range(0, size(p.steps)-1) AS i "
            "RETURN i AS step_index, p.steps[i] AS step_text, "
            "p.id AS sop_id, p.surface_form AS sop_name",
            wo_id=work_order_id)
        if direct:
            return direct

        # Path 2: via equipment the WO mentions
        return self._run(
            "MATCH (w:WorkOrder {surface_form: $wo_id})-[:MENTIONED_IN|MENTIONS*1..2]-(e:Equipment) "
            "MATCH (e)-[:FIXED_BY]->(p:Procedure) "
            "UNWIND range(0, size(p.steps)-1) AS i "
            "RETURN i AS step_index, p.steps[i] AS step_text, "
            "p.id AS sop_id, p.surface_form AS sop_name "
            "ORDER BY i LIMIT 50",
            wo_id=work_order_id)

    def work_order_details(self, work_order_id: str) -> dict:
        """Summary of a work order: description, linked equipment, status."""
        rows = self._run(
            "MATCH (w:WorkOrder {surface_form: $wo_id}) "
            "OPTIONAL MATCH (w)-[:MENTIONED_IN|MENTIONS*1..2]-(e:Equipment) "
            "RETURN w.surface_form AS wo_id, w.description AS description, "
            "w.action_taken AS action_taken, w.date AS date, "
            "collect(DISTINCT e.surface_form) AS equipment",
            wo_id=work_order_id)
        return rows[0] if rows else {}

    def close(self):
        self._driver.close()
