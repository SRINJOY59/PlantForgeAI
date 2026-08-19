"""Simulation limits and operating envelopes management endpoints.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gateway.auth import current_user
from gateway.deps import get_service, require_role
from plantmind_core.telemetry import get_logger

log = get_logger("gateway.routes.simulation.envelopes")

router = APIRouter()

# Container-then-repo, the same precedence the TEP watcher uses. parents[4]
# resolves to '/config' inside the image (the code lives at /srv/gateway/...),
# which does not exist - the config is mounted at /srv/config - so the mounted
# path is tried first and the repo path is the local-dev fallback.
_CONTAINER_ENVELOPE = Path("/srv/config/tep_envelopes.json")
_REPO_ENVELOPE = Path(__file__).resolve().parents[4] / "config" / "tep_envelopes.json"
_ENVELOPE_PATH = _CONTAINER_ENVELOPE if _CONTAINER_ENVELOPE.exists() else _REPO_ENVELOPE


def get_default_four_level_limits() -> dict:
    try:
        with open(_ENVELOPE_PATH) as f:
            envelopes = json.load(f)
    except Exception as e:
        log.error("failed to load tep_envelopes.json", error=str(e))
        envelopes = {}

    four_level = {}
    for tag_id, env in envelopes.items():
        if tag_id.startswith("_"):
            continue
        four_level[tag_id] = dict(env)

    return four_level


@router.get("/sim/envelopes")
def get_envelopes(svc=Depends(get_service)):
    """Returns the current four-level limits & setpoints from Redis or default JSON."""
    r = svc._bus._r
    try:
        cached = r.hgetall("sim:limits")
        if cached:
            return {k: json.loads(v) for k, v in cached.items()}

        defaults = get_default_four_level_limits()
        pipe = r.pipeline()
        for tag_id, limits in defaults.items():
            pipe.hset("sim:limits", tag_id, json.dumps(limits))
        pipe.execute()
        return defaults
    except Exception as e:
        log.error("Failed to fetch limits from Redis", error=str(e))
        return get_default_four_level_limits()


class LimitUpdate(BaseModel):
    ll: Optional[float] = None
    l: Optional[float] = None
    h: Optional[float] = None
    hh: Optional[float] = None
    setpoint: Optional[float] = None


@router.put("/sim/limits/{tag_id}", dependencies=[require_role("engineer")])
def update_limit(tag_id: str, limit_in: LimitUpdate, user: dict = Depends(current_user), svc=Depends(get_service)):
    r = svc._bus._r

    raw_limits = r.hget("sim:limits", tag_id)
    if not raw_limits:
        defaults = get_default_four_level_limits()
        if tag_id not in defaults:
            raise HTTPException(404, f"Tag {tag_id} not found in limits config")
        current = defaults[tag_id]
    else:
        current = json.loads(raw_limits)

    changes = {}
    for field in ["ll", "l", "h", "hh", "setpoint"]:
        new_val = getattr(limit_in, field)
        if new_val is not None:
            old_val = current.get(field)
            if old_val != new_val:
                current[field] = new_val
                changes[field] = {"old": old_val, "new": new_val}

    if not changes:
        return {"status": "no_changes", "limits": current}

    ll = current.get("ll")
    l = current.get("l")
    h = current.get("h")
    hh = current.get("hh")
    sp = current.get("setpoint")

    vals = [v for v in [ll, l, h, hh] if v is not None]
    if len(vals) > 1 and vals != sorted(vals):
        raise HTTPException(
            400,
            f"Invalid limit order. Must satisfy ll ({ll}) < l ({l}) < h ({h}) < hh ({hh})"
        )

    if sp is not None:
        if l is not None and sp <= l:
            raise HTTPException(400, f"Setpoint ({sp}) must be strictly greater than Low limit ({l})")
        if h is not None and sp >= h:
            raise HTTPException(400, f"Setpoint ({sp}) must be strictly less than High limit ({h})")

    r.hset("sim:limits", tag_id, json.dumps(current))

    audit_entry = {
        "user": user.get("email", "demo@local"),
        "tag_id": tag_id,
        "changes": changes,
        "timestamp": time.time(),
    }
    r.lpush("sim:limits:audit", json.dumps(audit_entry))
    r.ltrim("sim:limits:audit", 0, 49)

    r.publish("sim:limits:reload", json.dumps({"tag_id": tag_id, "limits": current}))

    log.info("limit updated", tag_id=tag_id, user=user.get("email"), changes=changes)
    return {"status": "updated", "limits": current}


@router.get("/sim/limits/audit")
def get_limits_audit(svc=Depends(get_service)):
    r = svc._bus._r
    try:
        entries = r.lrange("sim:limits:audit", 0, 49)
        return [json.loads(e) for e in entries]
    except Exception as e:
        log.error("Failed to fetch limits audit log", error=str(e))
        return []
