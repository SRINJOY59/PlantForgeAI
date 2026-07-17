"""SAP Plant Maintenance via OData (SAP Gateway).

Pulls maintenance orders/notifications and hands them to the pipeline as a
CSV. It deliberately does NOT rename SAP's fields (AUFNR, EQUNR, KTEXT...):
the table lane's MappingInferrer resolves alien headers onto our ontology
with one cheap LLM call, so a new SAP layout needs no code change here.

connectors.json:
  {"type": "sap", "id": "sap-pm",
   "base_url": "https://sap.example.com/sap/opu/odata/sap/ZPM_SRV",
   "entity": "MaintenanceOrderSet",
   "username_env": "SAP_USER", "password_env": "SAP_PASSWORD",
   "changed_field": "LastChangeDate"}
"""

import csv
import io
import os
from datetime import datetime, timezone

import httpx

from plantmind_core.telemetry import get_logger

from connectors.base import Connector, SyncItem

log = get_logger("connectors.sap")


class SapPmConnector(Connector):
    def __init__(self, id: str, base_url: str, entity="MaintenanceOrderSet",
                 username_env="SAP_USER", password_env="SAP_PASSWORD",
                 changed_field=None, plant=None, top=500, client=None):
        super().__init__(id)
        self._base = base_url.rstrip("/")
        self._entity = entity
        self._changed_field = changed_field
        self._plant = plant
        self._top = top
        # credentials come from the environment, never from the config file
        self._auth = (os.getenv(username_env, ""), os.getenv(password_env, ""))
        self._client = client

    def fetch(self, since: str):
        rows = self._query(since)
        if not rows:
            return
        marker = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = f"sap_{self._entity.lower()}_{marker}.csv"
        log.info("sap pull", entity=self._entity, rows=len(rows))
        yield SyncItem(filename=filename, data=_to_csv(rows), marker=marker)

    def _query(self, since: str) -> list:
        params = {"$format": "json", "$top": str(self._top)}
        filters = []
        if self._plant:
            filters.append(f"Plant eq '{self._plant}'")
        # incremental pull when the service exposes a change-stamp; without
        # one we re-pull and let the content-hash gate drop the duplicate
        if self._changed_field and since and since != "0":
            filters.append(f"{self._changed_field} gt datetime'{_odata_dt(since)}'")
        if filters:
            params["$filter"] = " and ".join(filters)

        client = self._client or httpx.Client(auth=self._auth, timeout=60)
        try:
            resp = client.get(f"{self._base}/{self._entity}", params=params)
            resp.raise_for_status()
            return _odata_rows(resp.json())
        finally:
            if self._client is None:
                client.close()


def _odata_rows(payload: dict) -> list:
    # v2 wraps results in d.results; v4 uses value
    if isinstance(payload.get("d"), dict):
        return payload["d"].get("results", [])
    if isinstance(payload.get("d"), list):
        return payload["d"]
    return payload.get("value", [])


def _to_csv(rows: list) -> bytes:
    fields = []
    for row in rows:
        for key, value in row.items():
            # drop OData's __metadata and nested navigation properties
            if key.startswith("__") or isinstance(value, (dict, list)):
                continue
            if key not in fields:
                fields.append(key)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k) for k in fields})
    return buf.getvalue().encode("utf-8")


def _odata_dt(since: str) -> str:
    """Our cursor is an ISO stamp; OData v2 wants datetime'YYYY-MM-DDTHH:MM:SS'."""
    try:
        return datetime.strptime(since, "%Y%m%dT%H%M%S").strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return since
