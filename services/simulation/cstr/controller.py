from __future__ import annotations
from dataclasses import dataclass
from simulation.base.pid import PIDController
from simulation.base.controller import BaseControllerBank
from simulation.cstr.topology import VESSELS

@dataclass
class FaultState:
    valve_clamp: float | None = None
    sensor_bias: float = 0.0
    gain_factor: float = 1.0

class CstrControllerBank(BaseControllerBank):
    """PID loop bank and fault manager for CSTR reactors."""
    
    DEFAULT_SETPOINTS: dict[str, float] = {
        "CSTR-101":  343.0,
        "CSTR-102A": 342.0,
        "CSTR-102B": 342.0,
        "CSTR-104":  340.0,
    }

    def __init__(self):
        self._pids = {
            v.tag: PIDController(
                setpoint=self.DEFAULT_SETPOINTS.get(v.tag, 343.0),
                Kp=1.2, Ki=0.3, Kd=0.2
            )
            for v in VESSELS
        }
        self._faults = {v.tag: FaultState() for v in VESSELS}

    def compute(self, true_state: dict) -> dict:
        """Compute cooling valve outputs based on the true physical temperature."""
        cmds = {}
        for tag, pid in self._pids.items():
            T_true = true_state[tag]["T"]
            fault = self._faults[tag]
            
            raw_cmd = pid.compute(T_true)
            degraded = raw_cmd * fault.gain_factor

            if fault.valve_clamp is not None:
                cmds[tag] = fault.valve_clamp
            else:
                cmds[tag] = max(0.0, min(100.0, degraded))
        return cmds

    def published_readings(self, true_state: dict, valve_outputs: dict) -> dict:
        """Apply sensor bias offsets to display/telemetry layers only."""
        readings = {}
        for tag in self._pids:
            fault = self._faults[tag]
            readings[tag] = {
                "Ca": true_state[tag]["Ca"],
                "T": true_state[tag]["T"] + fault.sensor_bias,
                "Tc": true_state[tag]["Tc"],
                "CoolantValve": valve_outputs[tag]
            }
        return readings

    def saturate_valve(self, tag: str, pct: float):
        self._faults[tag].valve_clamp = float(pct) if pct is not None else None

    def bias_sensor(self, tag: str, offset: float):
        self._faults[tag].sensor_bias = float(offset)

    def degrade_pid(self, tag: str, factor: float):
        self._faults[tag].gain_factor = float(max(0.0, factor))

    def clear_faults(self, tag: str | None = None):
        targets = [tag] if tag else list(self._faults.keys())
        for t in targets:
            self._faults[t] = FaultState()

    def reset_pids(self):
        for pid in self._pids.values():
            pid.reset()

    def active_faults(self) -> dict:
        out = {}
        for tag, f in self._faults.items():
            if f.valve_clamp is not None or f.sensor_bias != 0.0 or f.gain_factor != 1.0:
                out[tag] = {
                    "valve_clamp": f.valve_clamp,
                    "sensor_bias": f.sensor_bias,
                    "gain_factor": f.gain_factor,
                }
        return out
