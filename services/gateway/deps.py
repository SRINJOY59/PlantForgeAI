"""Shared singletons the routers pull in via Depends. main.py fills them in
at startup; tests override them with app.dependency_overrides."""

import json

from fastapi import Depends, HTTPException

from gateway.auth import ROLE_HIERARCHY, current_user

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


def require_role(*roles: str):
    """Dependency factory: asserts that the authenticated user holds at least
    one of the given roles (or any role above it in the hierarchy).

    Usage:
        @router.post("/ingest", dependencies=[require_role("engineer")])

    The check uses the hierarchy (operator < planner < engineer < admin),
    so require_role("engineer") also admits admin. Passing multiple roles
    is an OR, not an AND: require_role("planner", "engineer") admits either.
    """
    # Pre-compute the minimum rank accepted, not at call time but at decoration
    # time, so a typo in a role name raises immediately on import.
    for r in roles:
        if r not in ROLE_HIERARCHY:
            raise ValueError(f"Unknown role: {r!r}. Valid: {ROLE_HIERARCHY}")

    min_rank = min(ROLE_HIERARCHY.index(r) for r in roles)

    def _check(user: dict = Depends(current_user)):
        user_role = user.get("app_role", "operator")
        user_rank = ROLE_HIERARCHY.index(user_role) if user_role in ROLE_HIERARCHY else 0
        if user_rank < min_rank:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{user_role}' is not permitted here. "
                       f"Required: {' or '.join(roles)} (or higher).",
            )

    return Depends(_check)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

