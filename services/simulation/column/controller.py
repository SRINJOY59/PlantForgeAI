from __future__ import annotations
from dataclasses import dataclass, field
from simulation.base.pid import PIDController
from simulation.base.controller import BaseControllerBank

@dataclass
class ColumnFaultState:
    flooding_active: bool = False
    composition_bias: dict[int, float] = field(default_factory=dict)   # stage -> bias

class ColumnControllerBank(BaseControllerBank):
    """PID loop bank and fault manager for COLUMN-1."""

    def __init__(self):
        # Reflux PID targets x_D = 0.95
        self.reflux_pid = PIDController(
            setpoint=0.95, Kp=3.0, Ki=0.6, Kd=0.3, output_min=0.02, output_max=0.4
        )
        # Boilup PID targets x_B = 0.05
        self.boilup_pid = PIDController(
            setpoint=0.05, Kp=2.5, Ki=0.5, Kd=0.1, output_min=0.05, output_max=0.45
        )
        self.faults = ColumnFaultState()
        self.nominal_vapor_capacity = 0.5
        self.flooding_index = 0.0

    def compute(self, true_state: dict) -> dict:
        """Compute reflux L_R and vapor boilup V from TRUE liquid compositions."""
        x_profile = true_state["x"]
        x_0 = x_profile[0]
        x_11 = x_profile[11]

        L_R = self.reflux_pid.compute(x_0)
        V = self.boilup_pid.compute(-x_11)

        capacity = self.nominal_vapor_capacity
        if self.faults.flooding_active:
            capacity = 0.15

        self.flooding_index = V / capacity
        return {"L_R": L_R, "V": V}

    def published_readings(self, true_state: dict, valve_outputs: dict) -> dict:
        """Apply sensor bias offsets for display/telemetry layers only."""
        x_profile = true_state["x"]
        t_profile = true_state["T"]
        
        pub_x = []
        for stage, x_val in enumerate(x_profile):
            bias = self.faults.composition_bias.get(stage, 0.0)
            pub_x.append(float(max(0.0, min(1.0, x_val + bias))))
            
        return {
            "x": pub_x,
            "T": t_profile, # Boiling point temp profile
            "L_R": valve_outputs["L_R"],
            "V": valve_outputs["V"],
            "flooding_index": self.flooding_index
        }

    def saturate_valve(self, tag: str, pct: float):
        pass

    def bias_sensor(self, tag: str, offset: float):
        pass

    def degrade_pid(self, tag: str, factor: float):
        pass

    def flood_column(self, enabled: bool):
        self.faults.flooding_active = enabled

    def bias_composition_sensor(self, stage: int, offset: float):
        self.faults.composition_bias[stage] = offset

    def clear_faults(self, tag: str | None = None):
        self.faults = ColumnFaultState()
        self.flooding_index = 0.0

    def reset_pids(self):
        self.reflux_pid.reset()
        self.boilup_pid.reset()

    def active_faults(self) -> dict:
        out = {}
        if self.faults.flooding_active:
            out["flooding_active"] = True
        if self.faults.composition_bias:
            out["composition_bias"] = self.faults.composition_bias
        return out
