"""Where the tools' data actually comes from - two backends, split on purpose.

GatewayBackend goes through the HTTP gateway for anything with policy on it:
Q&A and change assessment carry rate limits and (when enabled) auth, and the
MCP path must not become a way around them.

GraphBackend reads Neo4j directly through AgentReader - the exact queries the
in-app agents run, corrections included. These are cheap reads with no policy
attached, and going through the gateway would just add a hop that does not
exist as an endpoint anyway.

The reader is created lazily: the server must start (and answer tools/list)
even when Neo4j is down, failing per-call instead of at launch - an MCP client
shows a broken tool call gracefully, but a server that dies on startup just
vanishes from the client's list.
"""

import httpx

from mcp_server.config import McpConfig


class GatewayBackend:
    def __init__(self, config: McpConfig):
        self._config = config

    def ask(self, question: str) -> dict:
        return self._post("/ask", {"question": question, "history": []},
                          timeout=120)

    def assess(self, tag: str, summary: str) -> dict:
        return self._post("/moc/assess", {"tag": tag, "summary": summary},
                          timeout=300)

    def metrics(self) -> dict:
        with httpx.Client(base_url=self._config.gateway_url,
                          timeout=15) as client:
            resp = client.get("/metrics", headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def _post(self, path: str, payload: dict, timeout: float) -> dict:
        with httpx.Client(base_url=self._config.gateway_url,
                          timeout=timeout) as client:
            resp = client.post(path, json=payload, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def _headers(self) -> dict:
        token = self._config.token
        return {"Authorization": f"Bearer {token}"} if token else {}


class GraphBackend:
    def __init__(self, reader=None):
        self._reader = reader

    def failure_history(self, tag: str) -> list:
        return self._get_reader().equipment_failures(f"equip:{tag}")

    def connected_equipment(self, tag: str) -> list:
        return self._get_reader().connected_equipment(tag)

    def governing_clauses(self, tag: str) -> list:
        return self._get_reader().governing_clauses(f"equip:{tag}")

    def documents_mentioning(self, tag: str) -> list:
        return self._get_reader().documents_mentioning(f"equip:{tag}")

    def fix_procedures(self, tag: str) -> list:
        return self._get_reader().procedures_for(tag)

    def work_orders(self, tag: str) -> list:
        return self._get_reader().work_orders_for(tag)

    def _get_reader(self):
        if self._reader is None:
            from agents.reader import AgentReader
            self._reader = AgentReader.from_settings()
        return self._reader
