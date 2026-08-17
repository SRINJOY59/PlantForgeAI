"""Tennessee Eastman Process — Physical Constants and Nominal Steady State.

Based on: Downs, J.J. and Vogel, E.F.,
"A Plant-Wide Industrial Process Control Problem,"
Computers & Chemical Engineering, 17(3), 245-255, 1993.

All values are normalised from the original paper's operating point.
Units: kmol, kPa, °C, m³, kJ unless noted.
"""
from __future__ import annotations
import numpy as np

# ─── Chemical species indices ───────────────────────────────────────────────
# A, B, C, D, E, F, G, H  (0-based index into mole fraction vectors)
A, B, C, D, E, F, G, H = 0, 1, 2, 3, 4, 5, 6, 7
N_SPECIES = 8

# ─── Reaction stoichiometry ──────────────────────────────────────────────────
# Reaction 1: A(g) + C(g) + D(g) → G(liq)       exothermic
# Reaction 2: A(g) + C(g) + E(g) → H(liq)       exothermic
# Reaction 3: A(g) + E(g) → F(liq)              exothermic (byproduct)
# Reaction 4: 3D(g) → 2F(liq)                   exothermic (byproduct)

# Stoichiometry matrices: [Nrx x Nspecies], negative = reactant
STOICH = np.array([
    [-1, 0, -1, -1,  0,  0,  1,  0],   # rx1: A+C+D→G
    [-1, 0, -1,  0, -1,  0,  0,  1],   # rx2: A+C+E→H
    [-1, 0,  0,  0, -1,  1,  0,  0],   # rx3: A+E→F
    [ 0, 0,  0, -3,  0,  2,  0,  0],   # rx4: 3D→2F
], dtype=float)

# ─── Reaction rate constants ─────────────────────────────────────────────────
# Rate law: r_j = k_j(T) * prod(x_i ^ nu_i) * P_total^n_order (simplified)
# We use Arrhenius: k_j(T) = k0_j * exp(-E_j / (R*T))  [T in Kelvin]
R_gas = 8.314e-3  # kJ / (mol·K)

# Pre-exponential factors (kmol/m³/s) at reference partial pressures
K0 = np.array([1.5214e10, 2.5629e10, 9.9215e09, 1.0000e08])

# Activation energies [kJ/mol]
EA = np.array([104.536, 107.278, 105.853, 44.0])

# Heat of reaction [kJ/kmol] (negative = exothermic)
DH_RX = np.array([-84.49e3, -143.4e3, -18.44e3, -66.82e3])

# ─── Vessel volumes ──────────────────────────────────────────────────────────
V_REACTOR   = 1333.0   # m³ reactor volume
V_SEPARATOR = 3574.0   # m³ separator volume
V_STRIPPER  = 156.5    # m³ stripper volume (base)

# ─── Heat transfer ───────────────────────────────────────────────────────────
# UA_j: overall heat-transfer conductance [kJ/h/°C]
UA_REACTOR   = 1.196e6   # reactor coolant coil
UA_CONDENSER = 1.827e6   # condenser

# ─── Nominal Steady-State Operating Point (Mode 1, IDV-0) ───────────────────
# From Table 1 of Downs & Vogel (1993), Mode 1 operating conditions
# These are the initial conditions for the ODE integrator.

# Reactor
NOMINAL_REACTOR_T     = 122.9    # °C
NOMINAL_REACTOR_P     = 2705.0   # kPa
NOMINAL_REACTOR_LEVEL = 75.0     # % (of max fill)

# Separator
NOMINAL_SEP_T         = 80.1     # °C
NOMINAL_SEP_P         = 2633.7   # kPa
NOMINAL_SEP_LEVEL     = 50.0     # %

# Stripper
NOMINAL_STRIP_T       = 65.7     # °C
NOMINAL_STRIP_P       = 2705.0   # kPa (tracks reactor)
NOMINAL_STRIP_LEVEL   = 50.0     # %

# Compressor recycle
NOMINAL_COMP_SPEED    = 22.89    # % (normalised)

# Feed flows [kmol/h]
NOMINAL_FEED_A  = 0.2506    # stream 1 (pure A)
NOMINAL_FEED_D  = 3664.0    # stream 2 (pure D)
NOMINAL_FEED_E  = 4509.0    # stream 3 (pure E)
NOMINAL_FEED_AC = 9.3477    # stream 4 (A/B/C mixture)

# Feed 4 composition (mole fractions)
FEED4_COMP = np.array([0.4850, 0.0050, 0.5100, 0.0, 0.0, 0.0, 0.0, 0.0])

# Product split: xG / (xG + xH) ≈ 0.5 nominal
NOMINAL_G_H_SPLIT = 0.5163

# Reactor vapour-phase nominal composition (mole fractions)
NOMINAL_XR = np.array([0.3294, 0.8709, 0.4290, 0.0039, 0.3696, 0.0004, 0.0012, 0.0])
# Normalise to sum to 1
NOMINAL_XR = NOMINAL_XR / NOMINAL_XR.sum()

# Separator vapour-phase nominal composition
NOMINAL_XS = np.array([0.3294, 0.8709, 0.4290, 0.0039, 0.3696, 0.0004, 0.0012, 0.0])
NOMINAL_XS = NOMINAL_XS / NOMINAL_XS.sum()

# Stripper liquid-phase nominal composition (product-rich)
NOMINAL_XST = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.54, 0.36])

# ─── Control valve nominal positions (%) ─────────────────────────────────────
NOMINAL_VALVES = {
    "D-FEED":         63.053,   # Stream 2 D feed valve
    "E-FEED":         53.980,   # Stream 3 E feed valve
    "A-FEED":         51.130,   # Stream 1 A feed valve
    "AC-FEED":        50.390,   # Stream 4 A/C feed valve
    "COMP-RECYCLE":   50.0,     # Compressor recycle valve
    "PURGE":          22.210,   # Purge valve
    "SEP-LIQ-OUT":    30.640,   # Separator liquid outlet
    "STRIP-LIQ-IN":   47.0,     # Stripper liquid inlet
    "STRIP-STEAM":    45.0,     # Stripper steam valve
    "REACTOR-COOL":   50.0,     # Reactor coolant valve
    "COND-COOL":      47.446,   # Condenser coolant valve
    "PRODUCT-SPLIT":  40.0,     # G/H product split valve
}

# ─── Sensor noise parameters ─────────────────────────────────────────────────
SIGMA_T    = 0.02    # °C standard deviation
SIGMA_P    = 0.5     # kPa
SIGMA_FLOW = 0.005   # kmol/h
SIGMA_COMP = 0.001   # mole-fraction

# ─── OU noise parameters for feed disturbances ───────────────────────────────
OU_THETA = 0.05
OU_SIGMA_FEED = 0.5  # % feed valve noise

# ─── Time constants ──────────────────────────────────────────────────────────
TAU_REACTOR  = 0.36   # h  (residence time at nominal conditions)
TAU_SEP      = 0.14   # h
TAU_STRIP    = 0.034  # h
