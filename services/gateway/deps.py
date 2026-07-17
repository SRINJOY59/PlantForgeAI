"""Shared singletons the routers pull in via Depends. main.py fills them in
at startup; tests override them with app.dependency_overrides."""

import json

_service = None
_http = None
_agents_http = None


def wire(service, http, agents_http=None):
    global _service, _http, _agents_http
    _service = service
    _http = http
    _agents_http = agents_http


def get_service():
    return _service


def get_http():
    return _http


def get_agents_http():
    """The agents service, not retrieval. A second client rather than a base_url
    juggled at the call site: the two upstreams have different timeouts and
    different failure meanings, and one client pretending to be both is how a
    Q&A timeout starts looking like an assessment failure."""
    return _agents_http


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
