"""Supabase JWT verification for the interview API, mirroring the gateway's
behaviour: auth is off when SUPABASE_JWT_SECRET is unset so local dev and the
demo run open. The WebRTC /api/offer endpoint instead treats possession of a
valid session_id as the credential (the browser transport POST cannot carry
the Supabase header)."""

import jwt
from fastapi import HTTPException, Request

from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger

log = get_logger("interview.auth")

_warned = False


def current_user(request: Request) -> dict:
    """FastAPI dependency: verifies the bearer token, returns its claims."""
    global _warned
    settings = get_settings()

    if not settings.supabase_jwt_secret:
        if not _warned:
            log.warning("SUPABASE_JWT_SECRET unset - interview API is OPEN")
            _warned = True
        return {"sub": "demo", "email": "demo@local", "demo": True}

    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "missing bearer token")

    try:
        return jwt.decode(token, settings.supabase_jwt_secret,
                          algorithms=["HS256"], audience="authenticated")
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "token expired")
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"invalid token: {str(e)[:80]}")
