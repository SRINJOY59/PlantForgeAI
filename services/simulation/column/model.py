from __future__ import annotations
import numpy as np
from scipy.integrate import solve_ivp
from simulation.base.model import BaseProcessModel

# Relative volatility — benzene (A) / toluene (B) at ~1 atm
alpha = 2.5

# Tray holdups (m3 equivalent kmol capacity)
M_condenser = 0.5
M_tray      = 0.1
M_reboiler  = 1.0

# Normal boiling points at 1 atm
T_boil_A = 353.3  # K  (benzene)
T_boil_B = 383.8  # K  (toluene)

def equilibrium(x):
    """Vapor mole fraction in equilibrium with liquid mole fraction x."""
    x = np.clip(x, 0.0, 1.0)
    return (alpha * x) / (1.0 + (alpha - 1.0) * x)

def stage_temperature(x):
    """Approximate boiling point of binary mixture linearly."""
    return T_boil_B - (T_boil_B - T_boil_A) * x

class ColumnModel(BaseProcessModel):
    """Dynamic binary distillation column solver."""

    def __init__(self, z_F_init: float = 0.5, feed_flow_init: float = 0.1):
        self.z_F       = z_F_init
        self.feed_flow = feed_flow_init
        self.x         = np.linspace(0.9, 0.1, 12)

    def _derivs(self, t, x, L_R, V):
        """Right-hand side of composition balances."""
        dxdt = np.zeros_like(x)
        y = equilibrium(x)

        F = self.feed_flow
        z_F = self.z_F

        L_rect = L_R
        L_strip = L_R + F

        # Stage 0: Condenser
        dxdt[0] = (V * (y[1] - x[0])) / M_condenser

        # Stages 1 to 5: Rectifying section trays
        for i in range(1, 6):
            dxdt[i] = (L_rect * (x[i-1] - x[i]) + V * (y[i+1] - y[i])) / M_tray

        # Stage 6: Feed tray
        dxdt[6] = (L_rect * x[5] - L_strip * x[6] + V * (y[7] - y[6]) + F * z_F) / M_tray

        # Stages 7 to 10: Stripping section trays
        for i in range(7, 11):
            dxdt[i] = (L_strip * (x[i-1] - x[i]) + V * (y[i+1] - y[i])) / M_tray

        # Stage 11: Reboiler
        dxdt[11] = (L_strip * (x[10] - x[11]) - V * (y[11] - x[11])) / M_reboiler

        return dxdt

    def step(self, dt: float, control_inputs: dict, disturbances: dict | None = None) -> dict:
        """Step the distillation column ODE.
        
        control_inputs: {"L_R": reflux_flow, "V": boilup_flow}
        disturbances: {"z_F": composition, "feed_flow": flow}
        """
        L_R = control_inputs.get("L_R", 0.1)
        V = control_inputs.get("V", 0.2)
        
        disturbances = disturbances or {}
        if "z_F" in disturbances:
            self.z_F = np.clip(disturbances["z_F"], 0.0, 1.0)
        if "feed_flow" in disturbances:
            self.feed_flow = max(0.0, disturbances["feed_flow"])

        sol = solve_ivp(
            self._derivs,
            t_span=(0.0, dt),
            y0=self.x,
            method="LSODA",
            args=(L_R, V),
            rtol=1e-5,
            atol=1e-7
        )

        if sol.success:
            self.x = np.clip(sol.y[:, -1], 0.0, 1.0)
            
        return self.get_state()

    def reset(self) -> None:
        self.x = np.linspace(0.9, 0.1, 12)

    def get_state(self) -> dict:
        return {
            "x": self.x.tolist(),
            "T": [float(stage_temperature(val)) for val in self.x]
        }
