"""SharePoint / OneDrive via Microsoft Graph.

Effectively a remote folder: walks a drive and pulls files changed since the
last sync, then hands the raw bytes to the pipeline - so the same classifier
routes a SharePoint PDF exactly like a local one.

Auth is app-only (client credentials); the secret comes from the environment.

connectors.json:
  {"type": "sharepoint", "id": "plant-docs",
   "tenant_id": "...", "client_id": "...",
   "secret_env": "SHAREPOINT_SECRET",
   "drive_id": "b!....", "folder": "/Maintenance"}
"""

import os
from datetime import datetime, timezone

import httpx

from plantmind_core.telemetry import get_logger

from connectors.base import Connector, SyncItem

log = get_logger("connectors.sharepoint")

GRAPH = "https://graph.microsoft.com/v1.0"
SKIP_EXT = (".lnk", ".url", ".tmp", ".ini")


class SharePointConnector(Connector):
    def __init__(self, id: str, tenant_id: str, client_id: str, drive_id: str,
                 secret_env="SHAREPOINT_SECRET", folder="/", max_files=100,
                 client=None):
        super().__init__(id)
        self._tenant = tenant_id
        self._client_id = client_id
        self._secret = os.getenv(secret_env, "")
        self._drive = drive_id
        self._folder = folder.strip("/")
        self._max = max_files
        self._client = client

    def fetch(self, since: str):
        client = self._client or httpx.Client(timeout=120)
        try:
            token = self._token(client)
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            for item in self._files(client, headers):
                modified = item.get("lastModifiedDateTime", "")
                name = item.get("name", "")
                if not modified or modified <= (since or ""):
                    continue
                if name.lower().endswith(SKIP_EXT):
                    continue
                data = self._download(client, headers, item)
                if data is None:
                    continue
                log.info("sharepoint file", name=name, modified=modified)
                yield SyncItem(filename=name, data=data, marker=modified)
        finally:
            if self._client is None:
                client.close()

    def _token(self, client) -> str:
        resp = client.post(
            f"https://login.microsoftonline.com/{self._tenant}/oauth2/v2.0/token",
            data={"client_id": self._client_id, "client_secret": self._secret,
                  "scope": "https://graph.microsoft.com/.default",
                  "grant_type": "client_credentials"})
        resp.raise_for_status()
        return resp.json().get("access_token", "")

    def _files(self, client, headers) -> list:
        path = (f"{GRAPH}/drives/{self._drive}/root:/{self._folder}:/children"
                if self._folder
                else f"{GRAPH}/drives/{self._drive}/root/children")
        resp = client.get(path, headers=headers)
        resp.raise_for_status()
        # ascending mtime so the runner's last marker is the newest seen
        files = [i for i in resp.json().get("value", []) if "file" in i]
        files.sort(key=lambda i: i.get("lastModifiedDateTime", ""))
        return files[:self._max]

    def _download(self, client, headers, item):
        url = item.get("@microsoft.graph.downloadUrl")
        try:
            # the download URL is pre-authorised, so it takes no auth header
            resp = (client.get(url) if url else
                    client.get(f"{GRAPH}/drives/{self._drive}/items/"
                               f"{item['id']}/content", headers=headers,
                               follow_redirects=True))
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            log.warning("sharepoint download failed",
                        name=item.get("name"), error=str(e)[:160])
            return None
