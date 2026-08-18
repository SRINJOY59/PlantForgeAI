from __future__ import annotations
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

log = logging.getLogger("simulation-runner")

# the alarm watcher listens here; see _announce_reset
RESET_CHANNEL = "sim:reset"

class FaultRequest(BaseModel):
    fault: str             # "saturate_valve" | "bias_sensor" | "degrade_pid" | "clear" | "flood_column" | "bias_composition_sensor"
    tag: Optional[str] = None
    value: Optional[float] = None
    stage: Optional[int] = None
    offset: Optional[float] = None
    enabled: Optional[bool] = None

class BaseSimulationRunner:
    """Generic simulation runner hosting FastAPI control API and async tick loop.
    
    Subclasses must implement the abstract `tick(self, dt: float)` method.
    """
    def __init__(self, model, bank, publisher, dt: float, port: int, title: str):
        self.model = model
        self.bank = bank
        self.publisher = publisher
        self.dt = dt
        self.port = port
        self.title = title

        self._running = False
        self._tick_count = 0
        self._sim_task: asyncio.Task | None = None
        self._sim_health = "nominal"

        # Construct FastAPI app
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            try:
                await self.sim_start()
            except Exception:
                # stdlib logger: no structlog-style kwargs here, they raise
                # TypeError out of the handler that was meant to contain this
                log.exception("Failed to auto-start simulation loop")
            yield
            await self.shutdown()

        self.app = FastAPI(title=self.title, lifespan=lifespan)
        
        # Wire routes
        self.app.post("/sim/start")(self.sim_start)
        self.app.post("/sim/stop")(self.sim_stop)
        self.app.post("/sim/reset")(self.sim_reset)
        self.app.post("/sim/fault")(self.sim_fault)
        self.app.get("/sim/status")(self.sim_status)
        self.app.get("/health")(self.health)

    async def tick(self, dt: float) -> None:
        """Advance simulation state by dt, execute PIDs, and publish telemetry."""
        raise NotImplementedError("Subclasses must override tick()")

    def on_reset(self) -> None:
        """Lifecycle hook on reset."""
        pass

    async def shutdown(self) -> None:
        """Clean shutdown handler."""
        self._running = False
        if self._sim_task and not self._sim_task.done():
            self._sim_task.cancel()
            try:
                await self._sim_task
            except asyncio.CancelledError:
                pass
        self._sim_task = None

    async def sim_start(self):
        if self._running:
            return {"status": "already_running", "tick": self._tick_count}
        self._running = True
        self._sim_task = asyncio.create_task(self._sim_loop())
        return {"status": "started"}

    async def sim_stop(self):
        self._running = False
        if self._sim_task and not self._sim_task.done():
            self._sim_task.cancel()
            try:
                await self._sim_task
            except asyncio.CancelledError:
                pass
        self._sim_task = None
        return {"status": "stopped", "tick": self._tick_count}

    async def sim_reset(self):
        self._running = False
        if self._sim_task and not self._sim_task.done():
            self._sim_task.cancel()
            try:
                await self._sim_task
            except asyncio.CancelledError:
                pass
        self._sim_task = None

        self._reset_to_nominal()

        # Auto-restart running loop from nominal steady-state
        self._running = True
        self._sim_task = asyncio.create_task(self._sim_loop())

        return {"status": "reset", "running": True}

    def _reset_to_nominal(self):
        """The reset itself, with no task management around it. sim_reset wraps
        this in stop/start; the tick loop calls it bare when it catches a
        divergence, because it is already the running task and must not cancel
        or recreate itself."""
        self.model.reset()
        self.bank.reset_pids()
        self.bank.clear_faults()
        self.on_reset()
        self._tick_count = 0
        self._sim_health = "nominal"

        # Publish nominal baseline immediately so the UI canvas/cards update instantly
        try:
            self.publisher.publish(self.model.state_dict(self.bank.mv))
        except Exception:
            log.exception("failed to publish reset telemetry")

        self._announce_reset()

    def _announce_reset(self):
        """Tell the alarm watcher the process is back at nominal.

        Reset drops every PV back inside its envelope in one step, so the
        watcher never sees the in-envelope samples that would normally clear
        the alarms it has open. Without this announcement those stale open
        alarms suppress the alert for the next fault injected after a reset —
        the operator injects an IDV, the process breaches, and nothing fires.
        The RCA claim keys go with them for the same reason."""
        try:
            r = self.publisher._r
            r.publish(RESET_CHANNEL, json.dumps({"at": time.time()}))
            claimed = list(r.scan_iter(match="rca:claimed:*", count=500))
            if claimed:
                r.delete(*claimed)
            log.info("simulation reset announced (%d RCA claims released)",
                     len(claimed))
        except Exception:
            log.exception("failed to announce simulation reset")

    async def sim_fault(self, req: FaultRequest):
        """Standardized fault injection router forwarding requests to banks."""
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
        elif req.fault == "flood_column":
            enabled = req.enabled if req.enabled is not None else True
            self.bank.flood_column(enabled)
        elif req.fault == "bias_composition_sensor":
            stage = req.stage if req.stage is not None else 0
            offset = req.offset if req.offset is not None else 0.0
            self.bank.bias_composition_sensor(stage, offset)
        elif req.fault == "clear":
            self.bank.clear_faults(req.tag)
        else:
            raise HTTPException(400, f"unknown fault type: {req.fault!r}")
        
        return {
            "status": "fault_injected", 
            "fault": req.fault,
            "tag": req.tag, 
            "value": req.value,
            "active_faults": self.bank.active_faults()
        }

    async def sim_status(self):
        status_data = {
            "running": self._running,
            "tick": self._tick_count,
            "sim_hz": 1.0 / self.dt,
            "sim_health": self._sim_health,
            "active_faults": self.bank.active_faults(),
        }
        # Add custom topology status if implemented by model subclass
        status_data.update(self.get_topology_status())
        return status_data

    def get_topology_status(self) -> dict:
        """Override to add custom vessel/tray state reports."""
        return {}

    async def health(self):
        return {"status": "ok", "running": self._running}

    async def _sim_loop(self):
        while self._running:
            tick_start = time.monotonic()
            try:
                await self.tick(self.dt)
            except Exception:
                log.exception("Simulation tick failed")
            else:
                # A diverged model is the one failure that does not raise: the
                # stiff solver just slows to a crawl on the next step and takes
                # the whole loop down with it. Catch the divergence here, while
                # the state is merely out of bounds, and reset before it can
                # reach the solver. Left running for months, this is what keeps
                # the sim - and the telemetry the historian depends on - alive.
                if not self._model_healthy():
                    log.error("simulation diverged at tick %d - "
                              "auto-resetting to nominal", self._tick_count)
                    self._sim_health = "diverged_reset"
                    self._reset_to_nominal()

            self._tick_count += 1
            elapsed = time.monotonic() - tick_start
            sleep = max(0.0, self.dt - elapsed)
            if sleep > 0:
                await asyncio.sleep(sleep)

    def _model_healthy(self) -> bool:
        """Divergence guard hook. Models that expose is_healthy() are checked;
        those that don't are assumed fine, so this stays a no-op for any
        simulation that hasn't opted in."""
        check = getattr(self.model, "is_healthy", None)
        if check is None:
            return True
        try:
            return bool(check())
        except Exception:
            # a broken health check must never be the thing that stops the sim
            log.exception("model health check raised; treating as healthy")
            return True

    def run(self):
        """Start the Uvicorn worker process."""
        uvicorn.run(self.app, host="0.0.0.0", port=self.port, log_level="info")
