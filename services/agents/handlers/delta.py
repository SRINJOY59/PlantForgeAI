"""Delta event handler: processes graph deltas, handles failure triggers,
drafts work orders, and updates speculative answer caches.
"""

import asyncio
from plantmind_core.schemas import Answer, Citation, GraphDelta, QueryMode
from plantmind_core.telemetry import get_logger
from agents.watchers import FailureWatcher

log = get_logger("agents.handlers.delta")


class DeltaHandler:
    def __init__(self, bus, reader, investigator, drafter, cache=None, embedder=None):
        self._bus = bus
        self._reader = reader
        self._investigator = investigator
        self._drafter = drafter
        self._cache = cache
        self._embedder = embedder
        self._failures = FailureWatcher(reader)

    def handle_delta(self, payload: str):
        delta = GraphDelta.model_validate_json(payload)
        # Invalidate cached answers touching modified nodes
        if self._cache:
            self._cache.invalidate(delta.touched_node_ids)

        if "HAS_FAILURE" not in delta.new_edge_types:
            return

        for trigger in self._failures.detect(delta.touched_node_ids, delta.graph_version):
            if not self._bus.claim_alert(f"failure:{trigger.tag}:{trigger.mode}:{trigger.count}"):
                continue
            asyncio.run(self._handle_trigger(trigger))

    async def _handle_trigger(self, trigger):
        alert, reasoned = await self._investigator.investigate_reasoned(trigger)
        self._reader.name_citations(alert.citations)
        self._bus.publish_alert(alert.model_dump_json())
        log.info("alert raised", kind=alert.kind, severity=alert.severity, title=alert.title)
        await self._draft_work_order(trigger, reasoned, alert.graph_version)
        await self._speculate(trigger, alert)

    async def _draft_work_order(self, trigger, reasoned, graph_version):
        try:
            draft = await self._drafter.draft(trigger, reasoned, graph_version)
            self._reader.name_citations(draft.citations)
            self._bus.publish_draft_work_order(draft.model_dump_json())
        except Exception as e:
            log.warning("work order drafting failed", tag=trigger.tag, error=str(e)[:200])

    async def _speculate(self, trigger, alert):
        if not (self._cache and self._embedder):
            return
        questions = [
            f"what should I do about {trigger.tag} {trigger.mode.lower()}?",
            f"{trigger.tag} failure history and recommendation",
            f"is the {trigger.tag} failure related to its sibling equipment?",
        ]
        answer = Answer(
            text=alert.body,
            citations=[Citation(doc_id=c.doc_id, snippet="") for c in alert.citations],
            mode=QueryMode.LOCAL,
            confidence="high" if alert.verified else "medium",
            graph_version=alert.graph_version,
        ).model_dump(mode="json")

        cited = [f"equip:{trigger.tag}"] + [f"equip:{s['tag']}" for s in trigger.siblings]
        embeddings = await self._embedder.embed(questions)
        for q, emb in zip(questions, embeddings):
            self._cache.put(q, emb, answer, cited)
        log.info("speculative answers cached", tag=trigger.tag, questions=len(questions))
