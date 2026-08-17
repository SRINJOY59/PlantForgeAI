"""TEP alarm handler: processes TEP watcher alerts, fetches live simulator status,
and performs LLM root cause analysis (RCA).
"""

import json
import os
import httpx
from plantmind_core.telemetry import get_logger
from agents.watchers import Trigger, family_of

log = get_logger("agents.handlers.tep_alarm")


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

        # Deduplicate
        rca_claim_key = f"rca:claimed:{fingerprint}"
        if not self._bus._r.set(rca_claim_key, "1", ex=3600, nx=True):
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

        log.info("RCA: TEP alarm investigation starting", tag_id=tag_id, level=level, idvs=active_idvs)

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
            log.error("RCA: TEP investigation failed", tag_id=tag_id, error=str(e))
