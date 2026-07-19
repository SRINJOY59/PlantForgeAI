"""Supabase JWT verification - the edge's job, and the reason the gateway
exists. The frontend can only attach a token; only this can decide it is
real. Domain services stay oblivious: they are not internet-facing.

Auth is off when SUPABASE_JWT_SECRET is unset, so local dev and the demo run
open. That is a deliberate escape hatch, and it announces itself in the logs.

Role model (app_role claim, stamped by the custom_jwt_claims Supabase hook):
  operator  – Ask, Alerts, Documents read             (new-user default)
  planner   – + Connectors read
  engineer  – + Graph, Compliance, MoC, Interview, document upload
  admin     – full access + Connectors write, role management
"""

import jwt
from fastapi import HTTPException, Request

from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger

log = get_logger("gateway.auth")

_warned = False

# Ordered from least to most privileged. Used by require_role() to support
# "engineer or above" comparisons without enumerating every tier.
ROLE_HIERARCHY = ["operator", "planner", "engineer", "admin"]


def auth_enabled() -> bool:
    return bool(get_settings().supabase_jwt_secret)


def _role_from_claims(claims: dict) -> str:
    """Pull app_role out of the JWT claims, with a safe default.

    The Supabase custom_jwt_claims hook nests it under 'app_metadata';
    some setups also put it directly at the top level. Check both.
    """
    app_meta = claims.get("app_metadata") or {}
    role = app_meta.get("app_role") or claims.get("app_role") or "operator"
    # Reject unknown values so a misconfigured hook doesn't silently elevate.
    return role if role in ROLE_HIERARCHY else "operator"


def current_user(request: Request) -> dict:
    """FastAPI dependency: verifies the bearer token, returns its claims.

    The returned dict always contains:
      sub       – user id
      email     – user email (may be empty in non-email flows)
      app_role  – one of operator / planner / engineer / admin
      demo      – True only in open / local-dev mode
    """
    global _warned
    settings = get_settings()

    if not settings.supabase_jwt_secret:
        if not _warned:
            log.warning("SUPABASE_JWT_SECRET unset - gateway is OPEN")
            _warned = True
        # Demo mode: engineer so every feature can be exercised locally.
        return {"sub": "demo", "email": "demo@local", "app_role": "engineer",
                "demo": True}

    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "missing bearer token")

    try:
        claims = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "token expired")
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"invalid token: {str(e)[:80]}")

    claims["app_role"] = _role_from_claims(claims)
    return claims

