"""Shared singletons the routers pull in via Depends. main.py fills them in
at startup; tests override them with app.dependency_overrides."""

import json

_service = None
_http = None


def wire(service, http):
    global _service, _http
    _service = service
    _http = http


def get_service():
    return _service


def get_http():
    return _http


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
