"""TEP alarm handler: processes TEP watcher alerts, fetches live simulator status,
and performs LLM root cause analysis (RCA).
"""

import json
import os
import httpx
from plantmind_core.telemetry import get_logger
from agents.watchers import Trigger, family_of

log = get_logger("agents.handlers.tep_alarm")

# long enough to cover a redelivery of the same stream entry, short enough
# that these keys do not accumulate across a long-running deployment
RCA_CLAIM_TTL_S = 3600


class TepAlarmHandler:
    def __init__(self, bus, reader, investigator):
        self._bus = bus
        self._reader = reader
        self._investigator = investigator

    async def handle_tep_alarm(self, entry_id: str, payload: dict):
        tag_id = payload.get("tag_id", "")
        unit_area = payload.get("unit", tag_id.split(".")[0] if "." in tag_id else tag_id)
        level = payload.get("level", "H")
        value = payload.get("value", 0.0)
        limit_val = payload.get("limit")
        fingerprint = payload.get("fingerprint", f"tep:{tag_id}:{level}")
        message = payload.get("message", "")

        # One investigation per alarm occurrence.
        #
        # Claimed on the stream entry, not on the fingerprint. A fingerprint
        # cooldown looks like the safe choice and is not: the watcher re-arms a
        # tag after 30s back inside its envelope, so an operator who clears a
        # fault and injects it again gets a second, genuine alarm inside the
        # cooldown of the first - the alert appears on the panel and no
        # investigation ever arrives beside it. Rate limiting is the watcher's
        # job, and its debounce already does it. This key exists only so a
        # redelivered entry is not investigated twice, which is what the TTL is
        # sized for.
        rca_claim_key = f"rca:claimed:{entry_id}:{fingerprint}"
        if not self._bus._r.set(rca_claim_key, "1", ex=RCA_CLAIM_TTL_S, nx=True):
            return

        # Fetch live TEP status for IDV context
        tep_status = {}
        try:
            tep_url = os.environ.get("TEP_SIM_URL", "http://tep-sim:8012")
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{tep_url}/sim/status", timeout=3.0)
                if resp.is_success:
                    tep_status = resp.json()
        except Exception as e:
            log.warning("RCA: could not fetch TEP status", error=str(e))

        active_idvs = tep_status.get("active_idvs", [])
        idv_descs = tep_status.get("idv_descriptions", [])

        alert_context = {
            "tag_id": tag_id,
            "unit_area": unit_area,
            "alarm_level": level,
            "value": value,
            "limit": limit_val,
            "message": message,
            "active_idvs": active_idvs,
            "idv_descriptions": idv_descs,
            "plant": "Tennessee Eastman Process (TEP)",
        }

        family = family_of(unit_area)
        siblings = self._reader.family_history(family, level, exclude_tag=unit_area)

        trigger = Trigger(
            tag=unit_area,
            mode=f"TEP {level} alarm: {tag_id}",
            count=1,
            family=family,
            siblings=siblings,
            graph_version=0,
        )

        log.info("RCA: TEP alarm investigation starting", tag_id=tag_id, alarm_level=level, idvs=active_idvs)

        try:
            alert_obj, reasoned = await self._investigator.investigate_reasoned(
                trigger, alert_context=alert_context
            )
            self._reader.name_citations(alert_obj.citations)

            investigation_payload = {
                "type": "investigation",
                "alert_ref": fingerprint,
                "summary": alert_obj.body,
                "affected_equipment": [unit_area],
                "unit_area": unit_area,
                "alarm_level": level,
                "tag_id": tag_id,
                "active_idvs": active_idvs,
                "idv_descriptions": idv_descs,
                "citations": [c.model_dump() for c in alert_obj.citations],
                "timestamp": payload.get("timestamp"),
            }
            self._bus.publish_alert(json.dumps(investigation_payload))
            log.info("RCA: TEP investigation published", fingerprint=fingerprint)
        except Exception as e:
            # Release the claim so the next delivery of this alarm can retry
            self._bus._r.delete(rca_claim_key)
            # error_type, not just the message: the failure that hid the
            # event-loop bug for so long was a RuntimeError whose str() said
            # "Event loop is closed", which reads like a shutdown race rather
            # than the every-call breakage it was
            log.error("RCA: TEP investigation failed", tag_id=tag_id,
                      error_type=type(e).__name__, error=str(e)[:300])
