import os
import json
import httpx
import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account
from plantmind_core.telemetry import get_logger
from connectors.base import Connector, SyncItem

log = get_logger("connectors.gdrive")
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
GDRIVE_API = "https://www.googleapis.com/drive/v3/files"

class GoogleDriveConnector(Connector):
    """Pulls documents from Google Drive using a Service Account."""
    def __init__(self, id: str, credentials_path_env="GDRIVE_CREDENTIALS_PATH", credentials_path: str = None,
                 folder_id: str = None, max_files=100, client=None):
        super().__init__(id)
        if credentials_path:
            self._cred_path = credentials_path
        else:
            self._cred_path = os.getenv(credentials_path_env, "")
        self._folder_id = folder_id
        self._max = max_files
        self._client = client

    def fetch(self, since: str):
        if not self._cred_path or not os.path.exists(self._cred_path):
            log.warning("gdrive credentials missing or invalid path", path=self._cred_path)
            return

        client = self._client or httpx.Client(timeout=120)
        try:
            creds = service_account.Credentials.from_service_account_file(
                self._cred_path, scopes=SCOPES)
            creds.refresh(GoogleAuthRequest())
            token = creds.token
            
            headers = {"Authorization": f"Bearer {token}"}
            
            # Build query
            query = f"modifiedTime > '{since}'" if since else ""
            if self._folder_id:
                folder_q = f"'{self._folder_id}' in parents"
                query = f"{query} and {folder_q}" if query else folder_q
                
            params = {
                "q": query,
                "orderBy": "modifiedTime",
                "pageSize": self._max,
                "fields": "files(id, name, modifiedTime)"
            }
            
            resp = client.get(GDRIVE_API, headers=headers, params=params)
            resp.raise_for_status()
            files = resp.json().get("files", [])
            
            for f in files:
                modified = f.get("modifiedTime", "")
                name = f.get("name", "")
                file_id = f.get("id", "")
                
                if not modified or modified <= (since or ""):
                    continue
                    
                # Download file bytes
                dl_resp = client.get(f"{GDRIVE_API}/{file_id}", params={"alt": "media"}, headers=headers)
                if dl_resp.status_code != 200:
                    log.warning("gdrive download failed", name=name, status=dl_resp.status_code)
                    continue
                    
                data = dl_resp.content
                log.info("gdrive file fetched", name=name, modified=modified)
                yield SyncItem(filename=name, data=data, marker=modified)
        finally:
            if self._client is None:
                client.close()
