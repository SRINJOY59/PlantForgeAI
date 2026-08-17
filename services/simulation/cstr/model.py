from __future__ import annotations
import numpy as np
from scipy.integrate import solve_ivp
from simulation.base.model import BaseProcessModel
from simulation.cstr.topology import VESSEL_MAP, feed_temperature_for

# ──────────────────────────────────────────────────────────────────────────────
# Physical constants (exothermic system)
# ──────────────────────────────────────────────────────────────────────────────
R = 8.314          # J / mol·K
k0 = 7.2e10        # 1/s  (pre-exponential factor)
Ea = 72_750.0      # J/mol
dHr = -5.0e4       # J/mol  (negative = exothermic)
V = 1.0            # m³  (reactor volume)
Vc = 0.14          # m³  (coolant jacket volume)
UA = 5_000.0       # W/K  (overall heat-transfer coefficient × area)
rho_Cp = 5.0e5     # J / m³·K  (density × specific heat, process)
rho_c_Cp_c = 4.2e6 # J / m³·K  (density × specific heat, coolant)
Tc0 = 300.0        # K  (coolant inlet temperature)
Ca0_default = 4.0  # mol/L
T0_default = 340.0 # K
q_feed = 0.1       # m³/s
Fc_max = 0.05      # m³/s at 100 % valve opening

def _k(T: float) -> float:
    """Arrhenius rate constant at temperature T [K]."""
    return k0 * np.exp(-Ea / (R * T))

def _odes(t, y, tau, Ca0, T0, Fc_cmd_pct):
    """Right-hand side of the three-state CSTR ODE."""
    Ca, T, Tc = y
    Ca = max(Ca, 0.0)        # non-negative guard
    T  = max(T,  250.0)      # keep Arrhenius from blowing up on numerical drift

    k  = _k(T)
    Fc = (Fc_cmd_pct / 100.0) * Fc_max   # m³/s

    dCa = (Ca0 - Ca) / tau  -  k * Ca
    dT  = (T0  - T)  / tau  \
          + (-dHr / rho_Cp) * k * Ca \
          - UA / (V * rho_Cp) * (T - Tc)
    dTc = (Fc / Vc) * (Tc0 - Tc)  \
          + UA / (Vc * rho_c_Cp_c) * (T - Tc)

    return [dCa, dT, dTc]

class CstrVessel:
    """One CSTR vessel model."""
    def __init__(self, tag: str,
                 Ca0: float = Ca0_default,
                 T0:  float = T0_default,
                 tau: float = V / q_feed,
                 Ca_init: float = 0.5,
                 T_init:  float = 340.0,
                 Tc_init: float = 305.0):
        self.tag   = tag
        self.Ca0   = Ca0
        self.T0    = T0
        self.tau   = tau
        self._state = np.array([Ca_init, T_init, Tc_init], dtype=float)

    @property
    def Ca(self) -> float:
        return float(self._state[0])

    @property
    def T(self) -> float:
        return float(self._state[1])

    @property
    def Tc(self) -> float:
        return float(self._state[2])

    def step(self, dt: float, valve_pct: float, T0_override: float | None = None) -> dict:
        T0 = T0_override if T0_override is not None else self.T0
        sol = solve_ivp(
            _odes,
            t_span=(0.0, dt),
            y0=self._state,
            method="LSODA",
            args=(self.tau, self.Ca0, T0, valve_pct),
            dense_output=False,
            rtol=1e-5,
            atol=1e-7,
        )
        if sol.success:
            self._state = sol.y[:, -1]
        return {"Ca": self.Ca, "T": self.T, "Tc": self.Tc}

    def reset(self, Ca: float = 0.5, T: float = 340.0, Tc: float = 305.0):
        self._state = np.array([Ca, T, Tc], dtype=float)

class CstrTrain(BaseProcessModel):
    """Coupled multi-reactor CSTR train."""
    def __init__(self):
        self.vessels = {
            tag: CstrVessel(
                tag=spec.tag,
                Ca0=spec.Ca0, T0=spec.T0, tau=spec.tau,
                Ca_init=spec.Ca_init, T_init=spec.T_init, Tc_init=spec.Tc_init,
            )
            for tag, spec in VESSEL_MAP.items()
        }
        self.prev_states = {}

    def step(self, dt: float, control_inputs: dict, disturbances: dict | None = None) -> dict:
        disturbances = disturbances or {}
        new_states = {}
        for tag, vessel in self.vessels.items():
            spec = VESSEL_MAP[tag]
            # Apply disturbances
            dCa0, dT0 = disturbances.get(tag, (0.0, 0.0))
            vessel.Ca0 = max(0.1, spec.Ca0 + dCa0)
            vessel.T0 = spec.T0 + dT0

            T0_override = feed_temperature_for(tag, self.prev_states)
            valve_pct = control_inputs.get(tag, 0.0)
            
            state = vessel.step(dt, valve_pct, T0_override)
            new_states[tag] = state

            # Restore nominal
            vessel.Ca0 = spec.Ca0
            vessel.T0 = spec.T0

        self.prev_states = new_states
        return new_states

    def reset(self) -> None:
        for vessel in self.vessels.values():
            spec = VESSEL_MAP[vessel.tag]
            vessel.reset(spec.Ca_init, spec.T_init, spec.Tc_init)
        self.prev_states = {}

    def get_state(self) -> dict:
        return {
            tag: {"Ca": v.Ca, "T": v.T, "Tc": v.Tc}
            for tag, v in self.vessels.items()
        }
