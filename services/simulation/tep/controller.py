"""Tennessee Eastman Process — Controller Bank.

Implements 12 regulatory PID loops plus IDV fault injection.
Inherits BasePIDController pattern from the unified simulation framework.
"""
from __future__ import annotations
import logging
from simulation.base.controller import BaseControllerBank
from simulation.base.pid import PIDController
from simulation.tep.constants import NOMINAL_VALVES
from simulation.tep.topology import IDV_TABLE


log = logging.getLogger("tep.controller")

# ─── IDV → fault state mapping ───────────────────────────────────────────────
# Maps IDV number to (fault_key, default_value, description)
IDV_FAULT_MAP: dict[int, tuple[str, float | bool, str]] = {
    1:  ("feed_ac_bias",   -200.0,  "A/C feed ratio step down"),
    2:  ("feed_ac_bias",   +150.0,  "B composition step up"),
    3:  ("feed_d_bias",    -300.0,  "D feed temperature step"),
    4:  ("cool_T_bias",    +5.0,    "Reactor coolant T step up"),
    5:  ("cond_cool_bias", +5.0,    "Condenser coolant T step up"),
    6:  ("feed_a_bias",    -50.0,   "A feed loss (step to 0)"),
    7:  ("feed_ac_bias",   -500.0,  "C header pressure loss"),
    8:  ("feed_ac_bias",   +80.0,   "A/B/C feed random var"),
    9:  ("feed_d_bias",    +50.0,   "D feed temp random var"),
    10: ("feed_ac_bias",   +30.0,   "C feed temp random var"),
    11: ("cool_T_bias",    +3.5,    "Reactor coolant random var"),
    12: ("cond_cool_bias", +3.5,    "Condenser coolant random var"),
    13: ("kinetics_drift", 0.85,    "Reaction kinetics slow drift"),
    14: ("cool_stuck",     True,    "Reactor coolant valve stuck"),
    15: ("cond_stuck",     True,    "Condenser coolant valve stuck"),
    16: ("ua_degradation", 0.3,     "Partial HX fouling"),
    17: ("feed_e_bias",    -200.0,  "E feed disturbance"),
    18: ("feed_d_bias",    +300.0,  "D feed surge"),
    19: ("kinetics_drift", 1.15,    "Runaway kinetics"),
    20: ("ua_degradation", 0.6,     "Severe HX fouling"),
    21: ("feed_ac_bias",   0.0,     "Stream 4 valve constant"),
}


class TepControllerBank(BaseControllerBank):
    """12 regulatory PID loops and IDV fault injection for TEP."""

    def __init__(self):
        # MV valve positions [%] — start at nominal
        self._mv: dict[str, float] = dict(NOMINAL_VALVES)
        # Active faults: fault_key → value
        self._faults: dict[str, float | bool] = {}
        # Sensor biases: tag_id → offset
        self._sensor_bias: dict[str, float] = {}
        # PID loops: tag_id → PID instance
        # We keep PIDs for key regulatory loops
        self._pids: dict[str, PIDController] = {
            "REACTOR.T":     PIDController(setpoint=122.9,  Kp=0.5,  Ki=0.05, Kd=0.0,  output_min=0.0, output_max=100.0),
            "REACTOR.P":     PIDController(setpoint=2705.0, Kp=0.3,  Ki=0.02, Kd=0.0,  output_min=0.0, output_max=100.0),
            "REACTOR.Level": PIDController(setpoint=75.0,   Kp=1.0,  Ki=0.1,  Kd=0.0,  output_min=0.0, output_max=100.0),
            "SEPARATOR.P":   PIDController(setpoint=2633.7, Kp=0.2,  Ki=0.01, Kd=0.0,  output_min=0.0, output_max=100.0),
            "SEPARATOR.Level":PIDController(setpoint=50.0,  Kp=1.0,  Ki=0.1,  Kd=0.0,  output_min=0.0, output_max=100.0),
            "STRIPPER.Level": PIDController(setpoint=50.0,  Kp=1.0,  Ki=0.1,  Kd=0.0,  output_min=0.0, output_max=100.0),
        }
        # PID degradation factors: tag → factor (1.0 = normal)
        self._pid_degrade: dict[str, float] = {}
        # Active IDV indices
        self._active_idvs: set[int] = set()

    def step(self, state: dict, dt: float) -> None:
        """Run all regulatory PID loops and update MV positions.

        Args:
            state: current state_dict from TepProcessModel.
            dt: integration step in seconds.
        """
        dt_h = dt / 3600.0

        # Reactor temperature → reactor coolant valve
        if "REACTOR.T" in state:
            meas_T = state["REACTOR.T"] + self._sensor_bias.get("REACTOR.T", 0.0)
            pid = self._pids["REACTOR.T"]
            factor = self._pid_degrade.get("REACTOR.T", 1.0)
            pid.Kp = 0.5 * factor
            out = pid.compute(meas_T)
            if "cool_stuck" not in self._faults:
                self._mv["REACTOR-COOL"] = float(out)

        # Reactor pressure → purge valve
        if "REACTOR.P" in state:
            meas_P = state["REACTOR.P"] + self._sensor_bias.get("REACTOR.P", 0.0)
            pid = self._pids["REACTOR.P"]
            out = pid.compute(meas_P)
            self._mv["PURGE"] = float(out)

        # Reactor level → D-feed valve
        if "REACTOR.Level" in state:
            meas_L = state["REACTOR.Level"] + self._sensor_bias.get("REACTOR.Level", 0.0)
            pid = self._pids["REACTOR.Level"]
            out = pid.compute(meas_L)
            self._mv["D-FEED"] = float(out)

        # Separator pressure → compressor recycle valve
        if "SEPARATOR.P" in state:
            meas_P = state["SEPARATOR.P"] + self._sensor_bias.get("SEPARATOR.P", 0.0)
            pid = self._pids["SEPARATOR.P"]
            out = pid.compute(meas_P)
            self._mv["COMP-RECYCLE"] = float(out)

        # Separator level → separator liquid outlet valve
        if "SEPARATOR.Level" in state:
            meas_L = state["SEPARATOR.Level"] + self._sensor_bias.get("SEPARATOR.Level", 0.0)
            pid = self._pids["SEPARATOR.Level"]
            out = pid.compute(meas_L)
            self._mv["SEP-LIQ-OUT"] = float(out)

        # Stripper level → stripper liquid inlet valve
        if "STRIPPER.Level" in state:
            meas_L = state["STRIPPER.Level"] + self._sensor_bias.get("STRIPPER.Level", 0.0)
            pid = self._pids["STRIPPER.Level"]
            out = pid.compute(meas_L)
            self._mv["STRIP-LIQ-IN"] = float(out)

    @property
    def mv(self) -> dict[str, float]:
        return dict(self._mv)

    # ─── Fault injection ──────────────────────────────────────────────────────

    def inject_idv(self, idv: int, active: bool = True) -> str:
        """Inject or clear an IDV fault by number (1-21)."""
        if idv not in IDV_FAULT_MAP:
            raise ValueError(f"IDV {idv} not defined (valid: 1-21)")
        fault_key, value, description = IDV_FAULT_MAP[idv]
        if active:
            self._faults[fault_key] = value
            self._active_idvs.add(idv)
            log.info("IDV injected", idv=idv, description=description)
        else:
            self._faults.pop(fault_key, None)
            self._active_idvs.discard(idv)
            log.info("IDV cleared", idv=idv)
        return description

    def saturate_valve(self, tag: str, value: float = 100.0) -> None:
        key = tag.replace("MV.", "")
        if key in self._mv:
            self._mv[key] = float(value)
            self._faults[f"valve_sat_{key}"] = value
            log.info("valve saturated", tag=tag, value=value)

    def bias_sensor(self, tag: str, offset: float = 5.0) -> None:
        self._sensor_bias[tag] = offset
        self._faults[f"sensor_bias_{tag}"] = offset
        log.info("sensor bias applied", tag=tag, offset=offset)

    def degrade_pid(self, tag: str, factor: float = 0.1) -> None:
        self._pid_degrade[tag] = max(0.0, min(1.0, factor))
        self._faults[f"pid_degrade_{tag}"] = factor
        log.info("PID degraded", tag=tag, factor=factor)

    def clear_faults(self, tag: str | None = None) -> None:
        if tag is None:
            self._faults.clear()
            self._sensor_bias.clear()
            self._pid_degrade.clear()
            self._active_idvs.clear()
            # reset PIDs
            for pid in self._pids.values():
                pid.reset()
        else:
            # Clear specific faults matching tag
            keys_to_del = [k for k in self._faults if tag.lower() in k.lower()]
            for k in keys_to_del:
                del self._faults[k]

    def active_faults(self) -> dict:
        result = dict(self._faults)
        result["_active_idvs"] = sorted(self._active_idvs)
        return result

    def reset_pids(self) -> None:
        for pid in self._pids.values():
            pid.reset()

    def get_fault_state(self) -> dict:
        """Return fault dict for passing into model ODE."""
        return dict(self._faults)
