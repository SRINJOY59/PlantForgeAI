"""TEP IDV fault injection endpoint.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from gateway.deps import require_role
from gateway.routes.simulation.proxy import proxy_request

router = APIRouter()

TEP_SIM_URL = os.environ.get("TEP_SIM_URL", "http://tep-sim:8012")


@router.post("/sim/{unit}/idv", dependencies=[require_role("engineer")])
async def inject_idv(unit: str, body: dict):
    """TEP IDV fault injection endpoint."""
    if unit == "tep":
        return await proxy_request(f"{TEP_SIM_URL}/sim/idv", json_data=body)
    raise HTTPException(400, f"Unknown unit: {unit}")
