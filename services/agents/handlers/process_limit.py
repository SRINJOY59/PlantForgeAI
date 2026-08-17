"""Process limit handler: processes process limit breaches from legacy/CSTR watchers
and performs LLM RCA investigations.
"""

import json
from plantmind_core.telemetry import get_logger
from agents.watchers import Trigger, family_of

log = get_logger("agents.handlers.process_limit")


class ProcessLimitHandler:
    def __init__(self, bus, reader, investigator):
        self._bus = bus
        self._reader = reader
        self._investigator = investigator

    async def handle_process_limit(self, entry_id: str, payload: dict):
        tag = payload.get("equipment")
        rule = payload.get("rule")
        fingerprint = payload.get("fingerprint")

        rca_claim_key = f"rca:claimed:{fingerprint}"
        if not self._bus._r.set(rca_claim_key, "1", ex=86400, nx=True):
            return

        family = family_of(tag)
        siblings = self._reader.family_history(family, rule, exclude_tag=tag)

        trigger = Trigger(
            tag=tag,
            mode=rule,
            count=1,
            family=family,
            siblings=siblings,
            graph_version=payload.get("graph_version", 0),
        )

        log.info("RCA: Starting LLM investigation for process limit breach", tag=tag, rule=rule, fingerprint=fingerprint)

        try:
            alert_obj, reasoned = await self._investigator.investigate_reasoned(trigger)
            self._reader.name_citations(alert_obj.citations)

            investigation_payload = {
                "type": "investigation",
                "alert_ref": fingerprint,
                "summary": alert_obj.body,
                "affected_equipment": [tag] + [s["tag"] for s in siblings],
                "citations": [c.model_dump() for c in alert_obj.citations],
                "timestamp": payload.get("timestamp"),
            }

            self._bus.publish_alert(json.dumps(investigation_payload))
            log.info("RCA: Investigation compiled and published", fingerprint=fingerprint)
        except Exception as e:
            log.error("RCA: Investigation failed", tag=tag, error=str(e))
