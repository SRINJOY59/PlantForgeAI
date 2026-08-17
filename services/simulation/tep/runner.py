"""Tennessee Eastman Process — Simulation Runner.

Wires TepProcessModel + TepControllerBank + TepTelemetryPublisher
into the BaseSimulationRunner FastAPI loop. Exposes TEP-specific
fault injection endpoint supporting IDV numbers 1-21.
"""
from __future__ import annotations
import logging
from fastapi import HTTPException
from simulation.base.runner import BaseSimulationRunner, FaultRequest
from simulation.tep.model import TepProcessModel
from simulation.tep.controller import TepControllerBank
from simulation.tep.publisher import TepTelemetryPublisher
from simulation.tep.topology import UNIT_AREAS, IDV_TABLE

log = logging.getLogger("tep.runner")


class TepRunner(BaseSimulationRunner):
    """Full TEP simulation runner with IDV fault injection."""

    def __init__(self, dt: float = 1.0, port: int = 8012):
        model = TepProcessModel()
        bank = TepControllerBank()
        publisher = TepTelemetryPublisher()
        super().__init__(
            model=model,
            bank=bank,
            publisher=publisher,
            dt=dt,
            port=port,
            title="Tennessee Eastman Process Simulator",
        )
        # Wire extra IDV endpoint
        self.app.post("/sim/idv")(self.sim_idv)

    async def tick(self, dt: float) -> None:
        """One simulation tick: run PIDs → step model → publish telemetry."""
        # 1. Get current state for PID feedback
        mv = self.bank.mv
        state = self.model.state_dict(mv)

        # 2. Run PID controllers
        self.bank.step(state, dt)

        # 3. Get updated MV and fault state
        mv_updated = self.bank.mv
        fault = self.bank.get_fault_state()

        # Apply fault state into model
        self.model._fault = fault

        # 4. Step ODE model
        self.model.step(dt, mv_updated)

        # 5. Publish telemetry
        new_state = self.model.state_dict(mv_updated)
        self.publisher.publish(new_state)

    async def sim_idv(self, req: dict):
        """Inject or clear an IDV fault (TEP-specific endpoint).

        Body: {"idv": int, "active": bool}
        """
        idv = int(req.get("idv", 0))
        active = bool(req.get("active", True))
        if idv < 1 or idv > 21:
            raise HTTPException(400, f"IDV must be 1-21, got {idv}")
        description = self.bank.inject_idv(idv, active)
        return {
            "status": "idv_injected" if active else "idv_cleared",
            "idv": idv,
            "description": description,
            "active_faults": self.bank.active_faults(),
        }

    async def sim_fault(self, req: FaultRequest):
        """Extended fault injection: standard faults + IDV shorthand."""
        # IDV injection via standard fault endpoint
        if req.fault.startswith("idv"):
            try:
                idv_num = int(req.fault.replace("idv", "").replace("-", "").replace("_", "").strip())
            except ValueError:
                raise HTTPException(400, f"Invalid IDV fault: {req.fault!r}")
            active = req.enabled if req.enabled is not None else True
            desc = self.bank.inject_idv(idv_num, active)
            return {
                "status": "fault_injected",
                "fault": req.fault,
                "idv": idv_num,
                "description": desc,
                "active_faults": self.bank.active_faults(),
            }

        # Standard faults
        if req.fault == "saturate_valve":
            if not req.tag:
                raise HTTPException(400, "tag required for saturate_valve")
            self.bank.saturate_valve(req.tag, req.value if req.value is not None else 100.0)
        elif req.fault == "bias_sensor":
            if not req.tag:
                raise HTTPException(400, "tag required for bias_sensor")
            self.bank.bias_sensor(req.tag, req.value if req.value is not None else 5.0)
        elif req.fault == "degrade_pid":
            if not req.tag:
                raise HTTPException(400, "tag required for degrade_pid")
            self.bank.degrade_pid(req.tag, req.value if req.value is not None else 0.1)
        elif req.fault == "clear":
            self.bank.clear_faults(req.tag)
        else:
            raise HTTPException(400, f"unknown fault type: {req.fault!r}")

        return {
            "status": "fault_injected",
            "fault": req.fault,
            "tag": req.tag,
            "value": req.value,
            "active_faults": self.bank.active_faults(),
        }

    def get_topology_status(self) -> dict:
        """Return per-unit area summary for /sim/status endpoint."""
        mv = self.bank.mv
        try:
            state = self.model.state_dict(mv)
        except Exception:
            state = {}
        area_status = {}
        for area in UNIT_AREAS:
            area_tags = {k: v for k, v in state.items() if k.startswith(area)}
            area_status[area] = area_tags
        idvs = sorted(self.bank._active_idvs)
        return {
            "unit_areas": area_status,
            "active_idvs": idvs,
            "idv_descriptions": [IDV_TABLE.get(i, "") for i in idvs],
        }

    def on_reset(self) -> None:
        """Clear model fault state on reset."""
        self.model._fault = {}
