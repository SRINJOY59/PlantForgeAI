"""Tennessee Eastman Process — ODE Process Model.

Implements a reduced-order TEP model faithful to the Downs & Vogel (1993)
benchmark. The state vector is intentionally condensed to ~20 key states
(compared to the original 50+) using lumped parameters, trading some
accuracy for real-time simulation at 1 Hz on modest hardware.

State vector (20 variables):
  [0]  REACTOR.T        °C   — reactor temperature
  [1]  REACTOR.P        kPa  — reactor pressure
  [2]  REACTOR.Level    %    — reactor liquid fill
  [3]  REACTOR.CoolT    °C   — reactor coolant temperature
  [4-11] REACTOR.x[A..H]     — reactor vapour mole fractions (8)
  [12] SEPARATOR.T      °C
  [13] SEPARATOR.P      kPa
  [14] SEPARATOR.Level  %
  [15] STRIPPER.T       °C
  [16] STRIPPER.Level   %
  [17] PRODUCT-SPLIT.xG     — product G mole fraction
  [18] PRODUCT-SPLIT.xH     — product H mole fraction
  [19] COMPRESSOR.Speed %
"""
from __future__ import annotations
import numpy as np
from scipy.integrate import solve_ivp
from simulation.base.model import BaseProcessModel
from simulation.tep.constants import (
    A, B, C, D, E, F, G, H, N_SPECIES,
    K0, EA, R_gas, DH_RX, STOICH,
    UA_REACTOR, UA_CONDENSER,
    V_REACTOR, V_SEPARATOR, V_STRIPPER,
    NOMINAL_REACTOR_T, NOMINAL_REACTOR_P, NOMINAL_REACTOR_LEVEL,
    NOMINAL_SEP_T, NOMINAL_SEP_P, NOMINAL_SEP_LEVEL,
    NOMINAL_STRIP_T, NOMINAL_STRIP_LEVEL,
    NOMINAL_COMP_SPEED, NOMINAL_XR,
    NOMINAL_G_H_SPLIT,
    TAU_REACTOR, TAU_SEP, TAU_STRIP,
    NOMINAL_VALVES,
    SIGMA_T, SIGMA_P, SIGMA_FLOW, SIGMA_COMP,
    OU_THETA, OU_SIGMA_FEED,
)

N_STATE = 20

# Nominal feed total flow [kmol/h] → converted to /s for ODE
F_TOTAL_NOMINAL = 1.0  # normalised unit flow


def _k(j: int, T_C: float) -> float:
    """Arrhenius rate constant for reaction j at temperature T [°C]."""
    T_K = T_C + 273.15
    return K0[j] * np.exp(-EA[j] / (R_gas * T_K))


def _reaction_rates(x: np.ndarray, T_C: float, P: float) -> np.ndarray:
    """Compute 4 reaction rates [kmol/m³/h].

    Simplified activity-based rate law proportional to partial pressures.
    """
    # Partial pressures (kPa), using ideal gas approximation
    pp = x * P  # shape (8,)

    # Reaction rates: r = k(T) * product of partial pressures of reactants
    r = np.zeros(4)
    # rx1: A+C+D→G
    r[0] = _k(0, T_C) * max(pp[A], 0) * max(pp[C], 0) * max(pp[D], 0) * 1e-6
    # rx2: A+C+E→H
    r[1] = _k(1, T_C) * max(pp[A], 0) * max(pp[C], 0) * max(pp[E], 0) * 1e-6
    # rx3: A+E→F
    r[2] = _k(2, T_C) * max(pp[A], 0) * max(pp[E], 0) * 1e-6
    # rx4: 3D→2F
    r[3] = _k(3, T_C) * max(pp[D], 0) ** 3 * 1e-9

    return r


def _odes(t: float, y: np.ndarray, mv: dict, fault: dict) -> np.ndarray:
    """Right-hand side of the TEP reduced-order ODE system."""
    dy = np.zeros(N_STATE)

    # Unpack state
    T_r   = float(np.clip(y[0], 50.0, 250.0))    # Reactor T [°C]
    P_r   = float(np.clip(y[1], 500.0, 5000.0))  # Reactor P [kPa]
    L_r   = float(np.clip(y[2], 5.0, 100.0))     # Reactor level [%]
    Tc_r  = float(np.clip(y[3], 5.0, 200.0))     # Coolant T [°C]
    xr    = np.clip(y[4:12], 0.0, 1.0)           # Reactor composition (8)
    T_s   = float(np.clip(y[12], 20.0, 150.0))
    P_s   = float(np.clip(y[13], 500.0, 4500.0))
    L_s   = float(np.clip(y[14], 5.0, 100.0))
    T_st  = float(np.clip(y[15], 30.0, 130.0))
    L_st  = float(np.clip(y[16], 5.0, 100.0))
    xG_p  = float(np.clip(y[17], 0.0, 1.0))
    xH_p  = float(np.clip(y[18], 0.0, 1.0))
    speed = float(np.clip(y[19], 10.0, 100.0))

    # Normalise reactor composition
    s = xr.sum()
    if s > 1e-9:
        xr = xr / s

    # ─── Feed flows from valve positions ────────────────────────────────────
    # Valve positions [%] → flow [kmol/h] (linear)
    v_d    = mv.get("D-FEED",        NOMINAL_VALVES["D-FEED"])
    v_e    = mv.get("E-FEED",        NOMINAL_VALVES["E-FEED"])
    v_a    = mv.get("A-FEED",        NOMINAL_VALVES["A-FEED"])
    v_ac   = mv.get("AC-FEED",       NOMINAL_VALVES["AC-FEED"])
    v_prg  = mv.get("PURGE",         NOMINAL_VALVES["PURGE"])
    v_rcl  = mv.get("COMP-RECYCLE",  NOMINAL_VALVES["COMP-RECYCLE"])
    v_sliq = mv.get("SEP-LIQ-OUT",   NOMINAL_VALVES["SEP-LIQ-OUT"])
    v_stin = mv.get("STRIP-LIQ-IN",  NOMINAL_VALVES["STRIP-LIQ-IN"])
    v_stst = mv.get("STRIP-STEAM",   NOMINAL_VALVES["STRIP-STEAM"])
    v_cool = mv.get("REACTOR-COOL",  NOMINAL_VALVES["REACTOR-COOL"])
    v_cond = mv.get("COND-COOL",     NOMINAL_VALVES["COND-COOL"])
    v_spl  = mv.get("PRODUCT-SPLIT", NOMINAL_VALVES["PRODUCT-SPLIT"])

    # Apply IDV faults to feed flows
    idv_bias_d    = fault.get("feed_d_bias", 0.0)
    idv_bias_e    = fault.get("feed_e_bias", 0.0)
    idv_bias_a    = fault.get("feed_a_bias", 0.0)
    idv_bias_ac   = fault.get("feed_ac_bias", 0.0)
    idv_cool_bias = fault.get("cool_T_bias", 0.0)
    idv_cond_bias = fault.get("cond_cool_bias", 0.0)
    idv_kin_drift = fault.get("kinetics_drift", 1.0)
    idv_cool_stuck = fault.get("cool_stuck", False)
    idv_cond_stuck = fault.get("cond_stuck", False)

    # Linear flow model (normalised to nominal)
    F_d  = (v_d  / 100.0) * 3664.0 + idv_bias_d    # kmol/h
    F_e  = (v_e  / 100.0) * 4509.0 + idv_bias_e
    F_a  = (v_a  / 100.0) * 0.2506 * 1000 + idv_bias_a   # scale up for units
    F_ac = (v_ac / 100.0) * 9.3477 * 100  + idv_bias_ac

    # Recycle flow from compressor (proportional to speed and recycle valve)
    F_recycle = (speed / 100.0) * (v_rcl / 100.0) * 1200.0  # kmol/h

    # Total feed to reactor
    F_feed_total = F_d + F_e + F_a + F_ac + F_recycle

    # Reactor residence time
    tau_r = V_REACTOR / max(F_feed_total, 1.0)  # h/m³ * m³ = h

    # ─── Reaction rates ──────────────────────────────────────────────────────
    r = _reaction_rates(xr, T_r, P_r) * idv_kin_drift
    # Net production rate per species [kmol/m³/h]
    net_prod = STOICH.T @ r  # shape (8,)

    # ─── Feed composition ────────────────────────────────────────────────────
    # Approximate feed composition (mole fractions weighted by flow)
    xfeed = np.zeros(8)
    if F_feed_total > 1e-9:
        xfeed[D] = F_d / F_feed_total
        xfeed[E] = F_e / F_feed_total
        xfeed[A] = F_a / F_feed_total
        # A/C/B from stream 4
        frac4 = F_ac / F_feed_total
        xfeed[A] += frac4 * 0.485
        xfeed[B] += frac4 * 0.005
        xfeed[C] += frac4 * 0.510
        xfeed[A] += (F_recycle / F_feed_total) * xr[A]  # recycle returns A
        xfeed[B] += (F_recycle / F_feed_total) * xr[B]

    # ─── Reactor dynamics ─────────────────────────────────────────────────────
    # Composition ODEs (simplified CSTR model per species)
    dxr = (xfeed - xr) / max(tau_r, 0.01) + net_prod / max(V_REACTOR / 1000, 1.0)
    dy[4:12] = dxr

    # Reactor heat balance
    heat_rx = np.dot(r, -DH_RX) * V_REACTOR / 3600  # kJ/s → W equivalent
    # Coolant duty
    T_cool_in = 20.0 + idv_cool_bias if not idv_cool_stuck else Tc_r
    cool_flow = (v_cool / 100.0) * 1000.0  # normalised flow
    UA_eff = UA_REACTOR * (1.0 - fault.get("ua_degradation", 0.0))
    Q_cool = UA_eff * (T_r - Tc_r) / 3600  # kJ/s

    # Coolant jacket ODE
    dTc_r = (cool_flow / 3600) * (T_cool_in - Tc_r) + Q_cool / 100
    dy[3] = np.clip(dTc_r, -50, 50)

    # Reactor T
    rho_Cp_r = 3500.0  # kJ/m³/°C (water-like liquid)
    dT_r = (heat_rx - Q_cool) / (V_REACTOR * rho_Cp_r / 1000)
    dy[0] = np.clip(dT_r, -5.0, 5.0)

    # Reactor pressure: driven by vapour generation and purge/recycle
    # Simplified: P tracks composition * RT
    T_K = T_r + 273.15
    P_r_target = (xr[A] + xr[B] + xr[C] + xr[D] + xr[E]) * 8.314 * T_K / 10.0
    dP_r = (P_r_target - P_r) * 0.1 - (v_prg / 100.0) * 5.0
    dy[1] = np.clip(dP_r, -100.0, 100.0)

    # Reactor level: integrating balance
    F_out_r = (L_r / 100.0) * F_feed_total * 0.3   # liquid drains
    dL_r = (F_feed_total * 0.2 - F_out_r) / V_REACTOR * 100
    dy[2] = np.clip(dL_r, -2.0, 2.0)

    # ─── Separator dynamics ──────────────────────────────────────────────────
    # Temperature lags reactor with condenser cooling
    T_cond_in = 25.0 + idv_cond_bias if not idv_cond_stuck else T_s
    Q_cond = UA_CONDENSER * (T_r - T_s) / 3600 * (v_cond / 100.0)
    dT_s = (T_r - T_s) * 0.05 - Q_cond / 5000 + (T_cond_in - T_s) * 0.001
    dy[12] = np.clip(dT_s, -2.0, 2.0)

    # Separator pressure tracks reactor with slight lag
    dP_s = (P_r - P_s) * 0.05
    dy[13] = np.clip(dP_s, -50.0, 50.0)

    # Separator level
    F_sep_in  = F_out_r
    F_sep_out = (v_sliq / 100.0) * 200.0  # to stripper
    F_vap_out = (speed / 100.0) * 900.0   # compressor draws vapour
    dL_s = (F_sep_in - F_sep_out - F_vap_out * 0.01) / V_SEPARATOR * 100
    dy[14] = np.clip(dL_s, -1.0, 1.0)

    # ─── Stripper dynamics ───────────────────────────────────────────────────
    steam_heat = (v_stst / 100.0) * 500.0  # kJ/h
    dT_st = (T_s - T_st) * 0.1 + steam_heat / 5000
    dy[15] = np.clip(dT_st, -1.0, 1.0)

    F_strip_in  = F_sep_out * (v_stin / 100.0)
    F_strip_out = (v_spl / 100.0) * 150.0
    dL_st = (F_strip_in - F_strip_out) / V_STRIPPER * 100
    dy[16] = np.clip(dL_st, -1.0, 1.0)

    # ─── Product split dynamics ──────────────────────────────────────────────
    # Product G and H fractions track reactor G/H with settling time
    target_xG = xr[G] / max(xr[G] + xr[H], 1e-6)
    target_xH = 1.0 - target_xG
    split_bias = (v_spl - 50.0) / 50.0 * 0.05  # valve bias ±5%
    dxG_p = (target_xG + split_bias - xG_p) * 0.2
    dxH_p = (target_xH - split_bias - xH_p) * 0.2
    dy[17] = np.clip(dxG_p, -0.05, 0.05)
    dy[18] = np.clip(dxH_p, -0.05, 0.05)

    # ─── Compressor speed ────────────────────────────────────────────────────
    # Compressor speed controlled to maintain recycle flow
    target_speed = (P_r - 2500.0) / 300.0 * 20.0 + 50.0  # pressure controller
    d_speed = (np.clip(target_speed, 10.0, 100.0) - speed) * 0.3
    dy[19] = np.clip(d_speed, -5.0, 5.0)

    return dy


# Any state component past this magnitude is divergence, not a fault. Normal
# operation and every IDV sit far below it (pressure, the largest, is ~3e3), so
# this only ever trips on a runaway integration - and it trips while the values
# are still finite, before they grow large enough to stall the LSODA solver.
STATE_SANE_MAX = 1e6


class TepProcessModel(BaseProcessModel):
    """Reduced-order Tennessee Eastman Process ODE model."""

    def __init__(self):
        self._state = self._nominal_state()
        self._fault: dict = {}
        # OU noise state for feeds
        self._ou_noise = np.zeros(4)  # A, D, E, AC feeds
        self._diverged = False

    def _nominal_state(self) -> np.ndarray:
        y0 = np.zeros(N_STATE)
        y0[0]  = NOMINAL_REACTOR_T
        y0[1]  = NOMINAL_REACTOR_P
        y0[2]  = NOMINAL_REACTOR_LEVEL
        y0[3]  = 20.0  # coolant inlet nominal
        y0[4:12] = NOMINAL_XR
        y0[12] = NOMINAL_SEP_T
        y0[13] = NOMINAL_SEP_P
        y0[14] = NOMINAL_SEP_LEVEL
        y0[15] = NOMINAL_STRIP_T
        y0[16] = NOMINAL_STRIP_LEVEL
        y0[17] = NOMINAL_G_H_SPLIT
        y0[18] = 1.0 - NOMINAL_G_H_SPLIT
        y0[19] = NOMINAL_COMP_SPEED
        return y0

    def reset(self) -> None:
        self._state = self._nominal_state()
        self._fault = {}
        self._ou_noise = np.zeros(4)
        self._diverged = False

    def is_healthy(self) -> bool:
        """False once the state has diverged - non-finite, past physical
        bounds, or a solve that refused its own result. The runner polls this
        after every tick and resets to nominal when it trips; that is what stops
        a runaway integration from reaching the solver and stalling it."""
        return (not self._diverged
                and bool(np.all(np.isfinite(self._state)))
                and float(np.max(np.abs(self._state))) < STATE_SANE_MAX)

    def step(self, dt: float, mv: dict) -> None:
        """Integrate one dt step (dt in seconds)."""
        # Never hand LSODA a diverged or non-finite state: the adaptive stiff
        # solver answers by collapsing its step size and can spin for minutes
        # inside one call, freezing the whole async sim loop. Hold instead and
        # let the runner reset us to nominal.
        if not self.is_healthy():
            self._diverged = True
            return

        # Update OU noise for feed disturbances
        dt_h = dt / 3600.0
        noise = np.random.randn(4) * OU_SIGMA_FEED
        self._ou_noise = self._ou_noise * (1 - OU_THETA) + noise

        sol = solve_ivp(
            _odes,
            t_span=(0.0, dt_h),
            y0=self._state,
            args=(mv, self._fault),
            method="LSODA",
            max_step=dt_h / 5,
            rtol=1e-4,
            atol=1e-6,
        )
        # Accept a finite result even if it is out of bounds - is_healthy() then
        # trips on the bounds and the runner resets before the next step inherits
        # it. A non-finite or failed solve is refused and flagged, so LSODA is
        # never re-entered on a NaN.
        if sol.success and np.all(np.isfinite(sol.y[:, -1])):
            self._state = sol.y[:, -1]
        else:
            self._diverged = True

    def state_dict(self, mv: dict) -> dict:
        """Return all tags as a flat dict with sensor noise applied."""
        y = self._state
        xr = y[4:12]
        s = xr.sum()
        if s > 1e-9:
            xr = xr / s

        def _n(v, sigma): return float(v) + np.random.randn() * sigma

        d: dict = {}
        # REACTOR
        d["REACTOR.T"]        = _n(y[0], SIGMA_T)
        d["REACTOR.P"]        = _n(y[1], SIGMA_P)
        d["REACTOR.Level"]    = _n(y[2], 0.1)
        d["REACTOR.CoolT"]    = _n(y[3], SIGMA_T)
        d["REACTOR.xA"]       = _n(xr[0] * 100, SIGMA_COMP * 100)
        d["REACTOR.xB"]       = _n(xr[1] * 100, SIGMA_COMP * 100)
        d["REACTOR.xC"]       = _n(xr[2] * 100, SIGMA_COMP * 100)
        d["REACTOR.xD"]       = _n(xr[3] * 100, SIGMA_COMP * 100)
        d["REACTOR.xE"]       = _n(xr[4] * 100, SIGMA_COMP * 100)
        d["REACTOR.xF"]       = _n(xr[5] * 100, SIGMA_COMP * 100)
        d["REACTOR.xG"]       = _n(xr[6] * 100, SIGMA_COMP * 100)
        d["REACTOR.xH"]       = _n(xr[7] * 100, SIGMA_COMP * 100)
        d["REACTOR.HeatDuty"] = float(np.dot(
            _reaction_rates(xr, y[0], y[1]),
            -DH_RX
        ) * 10.0)

        # CONDENSER
        d["CONDENSER.T"]       = _n((y[0] + y[12]) / 2, SIGMA_T)
        d["CONDENSER.P"]       = _n((y[1] + y[13]) / 2, SIGMA_P)
        d["CONDENSER.CoolT"]   = _n(y[3] * 0.8, SIGMA_T)
        d["CONDENSER.HeatDuty"]= abs(d["REACTOR.HeatDuty"]) * 0.6

        # SEPARATOR
        d["SEPARATOR.T"]       = _n(y[12], SIGMA_T)
        d["SEPARATOR.P"]       = _n(y[13], SIGMA_P)
        d["SEPARATOR.Level"]   = _n(y[14], 0.1)
        d["SEPARATOR.xG"]      = _n(y[17] * 100, SIGMA_COMP * 100)
        d["SEPARATOR.xH"]      = _n(y[18] * 100, SIGMA_COMP * 100)
        d["SEPARATOR.VapFlow"] = _n((y[19] / 100.0) * 900.0, SIGMA_FLOW)
        d["SEPARATOR.LiqFlow"] = _n(mv.get("SEP-LIQ-OUT", 30.0) / 100.0 * 200.0, SIGMA_FLOW)

        # STRIPPER
        d["STRIPPER.T"]        = _n(y[15], SIGMA_T)
        d["STRIPPER.P"]        = _n(y[13] * 0.98, SIGMA_P)
        d["STRIPPER.Level"]    = _n(y[16], 0.1)
        d["STRIPPER.xG"]       = _n(y[17] * 100 * 1.05, SIGMA_COMP * 100)
        d["STRIPPER.xH"]       = _n(y[18] * 100 * 1.05, SIGMA_COMP * 100)
        d["STRIPPER.Flow"]     = _n(mv.get("PRODUCT-SPLIT", 40.0) / 100.0 * 150.0, SIGMA_FLOW)

        # COMPRESSOR
        d["COMPRESSOR.Speed"]    = _n(y[19], 0.05)
        d["COMPRESSOR.Power"]    = _n(y[19] ** 2 / 100.0 * 120.0, 0.5)
        d["COMPRESSOR.RecycleF"] = _n(mv.get("COMP-RECYCLE", 50.0) / 100.0 * 1200.0, SIGMA_FLOW)

        # PRODUCT-SPLIT
        xG = float(np.clip(y[17], 0.0, 1.0))
        xH = float(np.clip(y[18], 0.0, 1.0))
        d["PRODUCT-SPLIT.xG"]     = _n(xG * 100, SIGMA_COMP * 100)
        d["PRODUCT-SPLIT.xH"]     = _n(xH * 100, SIGMA_COMP * 100)
        d["PRODUCT-SPLIT.TotalF"] = _n(d["STRIPPER.Flow"], SIGMA_FLOW)
        d["PRODUCT-SPLIT.Purity"] = _n((xG + xH) * 100 * 0.98, SIGMA_COMP * 100)

        # MV echo
        for k, v in mv.items():
            d[f"MV.{k}"] = float(v)

        return d

    def apply_fault(self, key: str, value) -> None:
        self._fault[key] = value

    def clear_fault(self, key: str | None = None) -> None:
        if key is None:
            self._fault.clear()
        else:
            self._fault.pop(key, None)

    def active_faults(self) -> dict:
        return dict(self._fault)


def _reaction_rates(x: np.ndarray, T_C: float, P: float) -> np.ndarray:
    """Re-exported for state_dict heat duty calculation."""
    from simulation.tep.constants import K0, EA, R_gas, A as _A, C as _C, D as _D, E as _E
    T_K = T_C + 273.15
    pp = x * P
    r = np.zeros(4)
    r[0] = K0[0] * np.exp(-EA[0] / (R_gas * T_K)) * max(pp[_A], 0) * max(pp[_C], 0) * max(pp[_D], 0) * 1e-6
    r[1] = K0[1] * np.exp(-EA[1] / (R_gas * T_K)) * max(pp[_A], 0) * max(pp[_C], 0) * max(pp[_E], 0) * 1e-6
    r[2] = K0[2] * np.exp(-EA[2] / (R_gas * T_K)) * max(pp[_A], 0) * max(pp[_E], 0) * 1e-6
    r[3] = K0[3] * np.exp(-EA[3] / (R_gas * T_K)) * max(pp[_D], 0) ** 3 * 1e-9
    return r
