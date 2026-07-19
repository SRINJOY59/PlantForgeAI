import os
import json
import httpx
from plantmind_core.telemetry import get_logger
from connectors.base import Connector, SyncItem

log = get_logger("connectors.upkeep")

class UpKeepConnector(Connector):
    """Pulls Work Orders from UpKeep CMMS using their REST API."""
    def __init__(self, id: str, token_env="UPKEEP_TOKEN", max_items=100, client=None):
        super().__init__(id)
        self._token = os.getenv(token_env, "")
        self._max = max_items
        self._client = client
        self.api_url = "https://api.onupkeep.com/api/v2/work-orders"

    def fetch(self, since: str):
        client = self._client or httpx.Client(timeout=60)
        try:
            if not self._token:
                log.warning("upkeep token missing", connector=self.id)
                return
            
            headers = {"Session-Token": self._token}
            resp = client.get(self.api_url, headers=headers)
            resp.raise_for_status()
            
            work_orders = resp.json().get("results", [])
            # Sort ascending by update time to satisfy runner idempotency
            work_orders.sort(key=lambda w: w.get("updatedAt", ""))
            
            for wo in work_orders[:self._max]:
                modified = wo.get("updatedAt", "")
                wo_id = wo.get("id", "")
                if not modified or modified <= (since or ""):
                    continue
                
                # Serialized JSON will be processed by the text classifier downstream
                filename = f"upkeep_wo_{wo_id}.json"
                data = json.dumps(wo).encode("utf-8")
                
                log.info("upkeep work order", id=wo_id, modified=modified)
                yield SyncItem(filename=filename, data=data, marker=modified)
        finally:
            if self._client is None:
                client.close()
