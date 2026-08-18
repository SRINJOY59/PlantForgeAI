"""Process limit handler: processes process limit breaches from legacy/CSTR watchers
and performs LLM RCA investigations.
"""

import json
from plantmind_core.telemetry import get_logger
from agents.watchers import Trigger, family_of

log = get_logger("agents.handlers.process_limit")

# covers a redelivery of the same stream entry, and no longer
RCA_CLAIM_TTL_S = 3600


class ProcessLimitHandler:
    def __init__(self, bus, reader, investigator):
        self._bus = bus
        self._reader = reader
        self._investigator = investigator

    async def handle_process_limit(self, entry_id: str, payload: dict):
        tag = payload.get("equipment")
        rule = payload.get("rule")
        fingerprint = payload.get("fingerprint")

        # Claimed per alarm occurrence, not per fingerprint - see the note in
        # tep_alarm.py. A day-long claim on the fingerprint meant a tag that
        # breached, recovered and breached again got its alert without an
        # investigation for the rest of the day.
        rca_claim_key = f"rca:claimed:{entry_id}:{fingerprint}"
        if not self._bus._r.set(rca_claim_key, "1", ex=RCA_CLAIM_TTL_S, nx=True):
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
            self._bus._r.delete(rca_claim_key)      # so a redelivery can retry
            log.error("RCA: Investigation failed", tag=tag,
                      error_type=type(e).__name__, error=str(e)[:300])
