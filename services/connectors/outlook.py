import os
import json
import httpx
from plantmind_core.telemetry import get_logger
from connectors.base import Connector, SyncItem

log = get_logger("connectors.outlook")
GRAPH = "https://graph.microsoft.com/v1.0"

class OutlookConnector(Connector):
    """Pulls emails from an Outlook shared mailbox using Microsoft Graph API."""
    def __init__(self, id: str, tenant_id: str, client_id: str, mailbox: str,
                 secret_env="SHAREPOINT_SECRET", folder="Inbox", max_emails=100,
                 client=None):
        super().__init__(id)
        self._tenant = tenant_id
        self._client_id = client_id
        self._secret = os.getenv(secret_env, "")
        self._mailbox = mailbox
        self._folder = folder
        self._max = max_emails
        self._client = client

    def fetch(self, since: str):
        client = self._client or httpx.Client(timeout=60)
        try:
            token = self._token(client)
            if not token:
                return
            headers = {"Authorization": f"Bearer {token}"}
            
            path = f"{GRAPH}/users/{self._mailbox}/mailFolders/{self._folder}/messages"
            resp = client.get(path, headers=headers)
            resp.raise_for_status()
            
            messages = resp.json().get("value", [])
            messages.sort(key=lambda m: m.get("receivedDateTime", ""))
            
            for msg in messages[:self._max]:
                received = msg.get("receivedDateTime", "")
                msg_id = msg.get("id", "")
                subject = msg.get("subject", "No Subject")
                if not received or received <= (since or ""):
                    continue
                
                # Convert to simple text format for ingestion
                body = msg.get("body", {}).get("content", "")
                content = f"Subject: {subject}\nDate: {received}\n\n{body}"
                data = content.encode("utf-8")
                filename = f"email_{msg_id}.txt"
                
                log.info("outlook email", subject=subject, received=received)
                yield SyncItem(filename=filename, data=data, marker=received)
        finally:
            if self._client is None:
                client.close()

    def _token(self, client) -> str:
        resp = client.post(
            f"https://login.microsoftonline.com/{self._tenant}/oauth2/v2.0/token",
            data={"client_id": self._client_id, "client_secret": self._secret,
                  "scope": "https://graph.microsoft.com/.default",
                  "grant_type": "client_credentials"})
        if resp.status_code != 200:
            log.warning("outlook token failed", status=resp.status_code)
            return ""
        return resp.json().get("access_token", "")
