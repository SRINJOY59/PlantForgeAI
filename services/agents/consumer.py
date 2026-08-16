"""The agents runtime: a long-lived process that tails the graph delta
stream and reacts. Event-driven (a delta fires the failure watcher) plus
periodic (compliance is swept on an interval). Alerts are deduped by
fingerprint and published to the alert stream for the UI to tail.

    python -m agents.consumer
"""

import asyncio
import time
from datetime import date

from plantmind_core.bus import RedisBus
from plantmind_core.schemas import Answer, Citation, GraphDelta, QueryMode
from plantmind_core.telemetry import get_logger

from agents.reader import AgentReader
from agents.usecases import (ComplianceScanner, InvestigatorAgent,
                             StandardsWatcher, WebRevisionSource,
                             WorkOrderDrafter)
from agents.watchers import FailureWatcher

log = get_logger("agents.consumer")

CURSOR = "agents-deltas"
COMPLIANCE_INTERVAL_S = 3600
# standards move a few times a decade, and each check is a billed web search
# against the open internet. Daily is already generous.
STANDARDS_INTERVAL_S = 86400


class AgentsRuntime:
    def __init__(self, bus, reader, investigator=None, cache=None,
                 embedder=None, compliance_interval=COMPLIANCE_INTERVAL_S,
                 standards=None, standards_interval=STANDARDS_INTERVAL_S,
                 block_ms=15000, drafter=None):
        self._bus = bus
        self._reader = reader          # kept: _emit names alert citations
        self._failures = FailureWatcher(reader)
        self._investigator = investigator or InvestigatorAgent(reader)
        self._drafter = drafter or WorkOrderDrafter()
        self._compliance = ComplianceScanner(reader)
        # optional: a plant on an air-gapped network has no web to watch, and
        # the rest of the runtime must not care
        self._standards = standards
        self._cache = cache            # speculative pre-fill + invalidation
        self._embedder = embedder
        self._interval = compliance_interval
        self._standards_interval = standards_interval
        self._block_ms = block_ms
        self._last_compliance = 0.0
        self._last_standards = 0.0

    @classmethod
    def from_settings(cls) -> "AgentsRuntime":
        from plantmind_core.cache import AnswerCache
        from plantmind_core.config import get_settings
        from plantmind_core.llm import get_embedder, get_llm

        bus = RedisBus.from_settings()
        reader = AgentReader.from_settings()
        standards = (StandardsWatcher(reader, bus, WebRevisionSource(get_llm()))
                     if get_settings().standards_watch_enabled else None)
        return cls(bus, reader, cache=AnswerCache.from_settings(),
                   embedder=get_embedder(), standards=standards)

    def run(self):
        log.info("agents runtime started")
        self.run_compliance()                      # sweep once on startup
        while True:
            self.tick()

    def tick(self):
        cursor = self._bus.get_cursor(CURSOR)
        for entry_id, payload in self._bus.read_deltas(cursor, self._block_ms):
            self._on_delta(payload)
            self._bus.set_cursor(CURSOR, entry_id)
        if time.time() - self._last_compliance >= self._interval:
            self.run_compliance()
        if self._standards and (time.time() - self._last_standards
                                >= self._standards_interval):
            self.run_standards_watch()

    def _on_delta(self, payload: str):
        delta = GraphDelta.model_validate_json(payload)
        # any change invalidates cached answers that depend on the touched
        # nodes, so a stale answer never outlives a change to its subject
        if self._cache:
            self._cache.invalidate(delta.touched_node_ids)

        if "HAS_FAILURE" not in delta.new_edge_types:
            return
        # deterministic detection, then agentic investigation per trigger
        for trigger in self._failures.detect(delta.touched_node_ids,
                                             delta.graph_version):
            if not self._bus.claim_alert(
                    f"failure:{trigger.tag}:{trigger.mode}:{trigger.count}"):
                continue
            asyncio.run(self._handle_trigger(trigger))

    async def _handle_trigger(self, trigger):
        alert, reasoned = await self._investigator.investigate_reasoned(trigger)
        self._reader.name_citations(alert.citations)
        self._bus.publish_alert(alert.model_dump_json())
        log.info("alert raised", kind=alert.kind, severity=alert.severity,
                 title=alert.title)
        await self._draft_work_order(trigger, reasoned, alert.graph_version)
        await self._speculate(trigger, alert)

    async def _draft_work_order(self, trigger, reasoned, graph_version):
        """The corrective action the investigation implies, as a draft for a
        planner to approve - never as something the agent commits itself.

        Isolated behind its own try because the alert has already been
        published by this point. A drafting failure must not take down the
        warning; the warning is the part nobody can afford to lose.
        """
        try:
            draft = await self._drafter.draft(trigger, reasoned, graph_version)
            self._reader.name_citations(draft.citations)
            self._bus.publish_draft_work_order(draft.model_dump_json())
        except Exception as e:
            log.warning("work order drafting failed", tag=trigger.tag,
                        error=str(e)[:200])

    async def _speculate(self, trigger, alert):
        """The optimisation: the investigation we just ran to make the alert
        IS the answer someone is about to ask for. Pre-fill the answer cache
        keyed on the questions they'll ask, so the query is an instant hit -
        an answer computed at write time, for free."""
        if not (self._cache and self._embedder):
            return
        questions = [
            f"what should I do about {trigger.tag} {trigger.mode.lower()}?",
            f"{trigger.tag} failure history and recommendation",
            f"is the {trigger.tag} failure related to its sibling equipment?",
        ]
        answer = Answer(
            text=alert.body,
            citations=[Citation(doc_id=c.doc_id, snippet="")
                       for c in alert.citations],
            mode=QueryMode.LOCAL,
            confidence="high" if alert.verified else "medium",
            graph_version=alert.graph_version).model_dump(mode="json")
        cited = [f"equip:{trigger.tag}"] + [f"equip:{s['tag']}"
                                            for s in trigger.siblings]
        embeddings = await self._embedder.embed(questions)
        for q, emb in zip(questions, embeddings):
            self._cache.put(q, emb, answer, cited)
        log.info("speculative answers cached", tag=trigger.tag,
                 questions=len(questions))

    def run_compliance(self):
        self._last_compliance = time.time()
        alerts = self._compliance.scan(date.today().isoformat(),
                                       self._bus.graph_version())
        self._emit(alerts)

    def run_standards_watch(self):
        """Reaches the open internet, so it is the one sweep allowed to fail
        without taking the runtime with it: a DNS blip on a daily check is not
        a reason to stop watching the graph."""
        self._last_standards = time.time()
        try:
            alerts = asyncio.run(
                self._standards.scan(self._bus.graph_version()))
        except Exception as e:
            log.warning("standards watch failed", error=str(e)[:160])
            return
        self._emit(alerts)

    def _emit(self, alerts: list):
        for alert in alerts:
            # name the sources before they hit the stream: every alert kind
            # flows through here, so this is the one place that makes all of
            # them readable and openable in the UI
            self._reader.name_citations(alert.citations)
            if self._bus.claim_alert(alert.fingerprint):
                self._bus.publish_alert(alert.model_dump_json())
                log.info("alert raised", kind=alert.kind,
                         severity=alert.severity, title=alert.title)


def main():
    AgentsRuntime.from_settings().run()


if __name__ == "__main__":
    main()
