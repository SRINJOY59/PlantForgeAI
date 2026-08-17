"""Simulation proxy control endpoints (start, stop, reset, status, fault).
"""

from __future__ import annotations

import os
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gateway.deps import require_role

router = APIRouter()

TEP_SIM_URL = os.environ.get("TEP_SIM_URL", "http://tep-sim:8012")


class FaultPayload(BaseModel):
    fault: str
    tag: Optional[str] = None
    stage: Optional[int] = None
    value: Optional[float] = None


async def proxy_request(url: str, method: str = "POST", json_data: dict | None = None):
    async with httpx.AsyncClient() as client:
        try:
            if method == "POST":
                res = await client.post(url, json=json_data, timeout=5.0)
            else:
                res = await client.get(url, timeout=5.0)
            if not res.is_success:
                raise HTTPException(res.status_code, f"Simulator error: {res.text}")
            return res.json()
        except httpx.RequestError as exc:
            raise HTTPException(503, f"Simulator service unreachable: {exc}")


@router.post("/sim/{unit}/start", dependencies=[require_role("engineer")])
async def start_sim(unit: str):
    if unit == "tep":
        return await proxy_request(f"{TEP_SIM_URL}/sim/start")
    raise HTTPException(400, f"Unknown unit: {unit}")


@router.post("/sim/{unit}/stop", dependencies=[require_role("engineer")])
async def stop_sim(unit: str):
    if unit == "tep":
        return await proxy_request(f"{TEP_SIM_URL}/sim/stop")
    raise HTTPException(400, f"Unknown unit: {unit}")


@router.post("/sim/{unit}/reset", dependencies=[require_role("engineer")])
async def reset_sim(unit: str):
    if unit == "tep":
        return await proxy_request(f"{TEP_SIM_URL}/sim/reset")
    raise HTTPException(400, f"Unknown unit: {unit}")


@router.post("/sim/{unit}/fault", dependencies=[require_role("engineer")])
async def inject_fault(unit: str, payload: FaultPayload):
    if unit == "tep":
        return await proxy_request(f"{TEP_SIM_URL}/sim/fault", json_data=payload.model_dump(exclude_none=True))
    raise HTTPException(400, f"Unknown unit: {unit}")


@router.get("/sim/{unit}/status")
async def get_sim_status(unit: str):
    if unit == "tep":
        return await proxy_request(f"{TEP_SIM_URL}/sim/status", method="GET")
    raise HTTPException(400, f"Unknown unit: {unit}")
