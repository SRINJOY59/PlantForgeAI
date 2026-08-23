# Appendix A2 — Process Simulation: Governing Equations

Three process models run as live digital twins. Source of truth:
`services/simulation/{tep,cstr,column,base}/`. All integrate with
`scipy.integrate.solve_ivp` (RK45) on a 1 Hz wall-clock tick.

---

## A2.1 Simulation stack

```
   ┌──────────────────────────────────────────────────────────────┐
   │  runner.py      wall-clock loop, 1 Hz                        │
   │      │                                                        │
   │      ├─▶ controller.py   PID bank  →  MV vector u(t)         │
   │      │                                                        │
   │      ├─▶ model.py        solve_ivp(f, [t, t+dt], y)  →  y(t+dt)│
   │      │                    RK45, adaptive step                 │
   │      │                                                        │
   │      └─▶ publisher.py    tags → Redis Stream → historian      │
   └──────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                        Timescale hypertable  +  alarm watcher
```

---

## A2.2 CSTR — exothermic reactor with cooling jacket

Three states `y = [C_A, T, T_c]`. The canonical runaway-risk system: an
exothermic reaction whose rate rises with temperature, cooled by a jacket whose
own temperature is a state.

**Kinetics (Arrhenius):**

```
                       ⎛   −Eₐ  ⎞
    k(T)  =  k₀ · exp  ⎜ ─────── ⎟
                       ⎝  R · T  ⎠
```

**Governing system:**

```
    dC_A     C_A0 − C_A
    ────  =  ──────────  −  k(T) · C_A
     dt          τ
             └────┬────┘     └───┬───┘
              convection      consumption

    dT       T₀ − T        (−ΔH_r)                 U·A
    ──   =   ──────   +   ─────────· k(T)·C_A  −  ───────·(T − T_c)
    dt          τ           ρ·C_p                  V·ρ·C_p
             └──┬──┘        └────┬────┘            └───┬───┘
             convection      reaction heat        jacket removal

    dT_c      F_c                       U·A
    ────  =  ─────·(T_c0 − T_c)  +  ────────────·(T − T_c)
     dt       V_c                    V_c·ρ_c·C_pc
             └──────┬──────┘         └─────┬─────┘
              coolant throughput     heat picked up
```

**Manipulated variable:** `F_c = (u/100)·F_c,max`, u = jacket valve %.

**Parameters** (`services/simulation/cstr/model.py`):

```
    k₀      = 7.2 × 10¹⁰  s⁻¹        UA        = 5 000    W/K
    Eₐ      = 72 750      J/mol      ρ·C_p     = 5.0×10⁵  J/m³·K
    ΔH_r    = −5.0 × 10⁴  J/mol      ρ_c·C_pc  = 4.2×10⁶  J/m³·K
    R       = 8.314       J/mol·K    T_c0      = 300      K
    V       = 1.0         m³         C_A0      = 4.0      mol/L
    V_c     = 0.14        m³         q_feed    = 0.1      m³/s
    τ       = V/q_feed = 10 s        F_c,max   = 0.05     m³/s
```

The `(−ΔH_r/ρC_p)·k(T)·C_A` term is positive and superlinear in `T` through
Arrhenius, while removal `−UA(T−T_c)/(VρC_p)` is only linear. Where the
generation curve escapes the removal line, the steady state is lost — this is
the thermal-runaway regime the alarm watcher is trained on.

---

## A2.3 Binary distillation column — 12 stages

State `x ∈ ℝ¹²`, liquid mole fraction of the light key per stage. Stage 0 is
the condenser, stage 6 the feed, stage 11 the reboiler.

**Vapour–liquid equilibrium (constant relative volatility α = 2.5):**

```
                α · xᵢ
    yᵢ  =  ─────────────────────
           1 + (α − 1) · xᵢ
```

**Stage material balances:**

```
  condenser      dx₀      V·(y₁ − x₀)
  (i = 0)        ───  =  ─────────────
                  dt        M_cond

  rectifying     dxᵢ      L_R·(xᵢ₋₁ − xᵢ)  +  V·(yᵢ₊₁ − yᵢ)
  (1 ≤ i ≤ 5)    ───  =  ────────────────────────────────────
                  dt                  M_tray

  feed stage     dx₆      L_R·x₅ − L_S·x₆ + V·(y₇ − y₆) + F·z_F
  (i = 6)        ───  =  ─────────────────────────────────────────
                  dt                     M_tray

  stripping      dxᵢ      L_S·(xᵢ₋₁ − xᵢ)  +  V·(yᵢ₊₁ − yᵢ)
  (7 ≤ i ≤ 10)   ───  =  ────────────────────────────────────
                  dt                  M_tray

  reboiler       dx₁₁     L_S·(x₁₀ − x₁₁)  −  V·(y₁₁ − x₁₁)
  (i = 11)       ────  =  ────────────────────────────────────
                  dt                  M_reb
```

with internal flows `L_R` (reflux, MV), `L_S = L_R + F` (stripping liquid),
`V` (boil-up, MV), and holdups `M_cond = 0.5`, `M_tray = 0.1`, `M_reb = 1.0`.

**Column profile** — the two operating lines and the equilibrium curve are what
the McCabe–Thiele panel renders live:

```
  y ▲                                            ╱
  1 ┤                              ╭────────────╱  y = x
    │                        ╭─────╯         ╱
    │                   ╭────╯            ╱      equilibrium
    │              ╭────╯              ╱         y = αx/(1+(α−1)x)
    │         ╭────╯      ╱─────────╱
    │     ╭───╯      ╱───╯   ← rectifying line
    │  ╭──╯     ╱───╯
    │╭─╯   ╱───╯  ← stripping line
  0 ┼──────────────────────────────────────────▶ x
    0                q = feed stage             1
```

---

## A2.4 Tennessee Eastman Process — 20-state reduced order

Faithful to Downs & Vogel (1993), condensed from 50+ states to 20 by lumping,
so it runs at 1 Hz on modest hardware.

**State vector:**

```
  idx  tag                  unit    idx  tag                    unit
  ───  ───────────────────  ─────   ───  ─────────────────────  ─────
   0   REACTOR.T            °C       12  SEPARATOR.T            °C
   1   REACTOR.P            kPa      13  SEPARATOR.P            kPa
   2   REACTOR.Level        %        14  SEPARATOR.Level        %
   3   REACTOR.CoolT        °C       15  STRIPPER.T             °C
  4–11 REACTOR.x[A…H]       mol frac 16  STRIPPER.Level         %
                                     17  PRODUCT.xG             mol frac
                                     18  PRODUCT.xH             mol frac
                                     19  COMPRESSOR.Speed       %
```

**Reaction network** — 4 gas-phase reactions over 8 species A…H:

```
    r₁ :  A + C + D  ──▶  G          (product)
    r₂ :  A + C + E  ──▶  H          (product)
    r₃ :  A + E      ──▶  F          (byproduct)
    r₄ :  3 D        ──▶  2 F        (byproduct)
```

**Rate laws** (activity-based, partial pressures `pᵢ = xᵢ·P`):

```
    r₁ = k₁(T)·p_A·p_C·p_D·10⁻⁶        r₃ = k₃(T)·p_A·p_E·10⁻⁶
    r₂ = k₂(T)·p_A·p_C·p_E·10⁻⁶        r₄ = k₄(T)·p_D³ ·10⁻⁹

                          ⎛  −E_a,j    ⎞
    k_j(T)  =  k₀,j · exp ⎜ ────────── ⎟ ,   T_K = T[°C] + 273.15
                          ⎝  R · T_K   ⎠
```

**Species balance** (CSTR form, `S` = stoichiometry matrix):

```
    dx      x_feed − x                 Sᵀ r
    ──  =  ────────────   +   ──────────────────────
    dt         τ_r              V_reactor / 1000

                    V_reactor
    with    τ_r  =  ──────────── ,   F_total = Σ F_feed + F_recycle
                    max(F_total, 1)
```

**Reactor energy balance:**

```
                                                   V_reactor
    Q_rx    =  ⟨ r , −ΔH_rx ⟩ · ──────────                  [heat released]
                                     3600

    Q_cool  =  UA_eff · (T_r − T_c) / 3600 ,  UA_eff = UA·(1 − f_foul)

    dT_r          Q_rx − Q_cool
    ────   =   ───────────────────────         clipped to ±5 °C/s
     dt        V_reactor · ρC_p / 1000

    dT_c        F_cool                    Q_cool
    ────  =  ──────────·(T_cool,in − T_c) + ──────    clipped to ±50 °C/s
     dt         3600                        100
```

**Pressure and levels** (integrating balances):

```
    P_target = (x_A + x_B + x_C + x_D + x_E) · R · T_K / 10

    dP_r
    ────  =  (P_target − P_r)·0.1  −  (v_purge/100)·5.0
     dt

    dL_r      F_total·0.2 − F_out          F_out = (L_r/100)·F_total·0.3
    ────  =  ──────────────────── · 100
     dt          V_reactor
```

**Manipulated variables (12 valves):**

```
   D-FEED   E-FEED   A-FEED   AC-FEED   PURGE   COMP-RECYCLE
   SEP-LIQ-OUT   STRIP-LIQ-IN   STRIP-STEAM   REACTOR-COOL
   COND-COOL   PRODUCT-SPLIT
```

**Disturbance vector (IDV faults)** injected into the RHS — this is what the
diagnostics agent is asked to identify from tag traces alone:

```
   feed_d_bias  feed_e_bias  feed_a_bias  feed_ac_bias   step bias on feed
   cool_T_bias  cond_cool_bias                           utility temp drift
   kinetics_drift                                        catalyst decay ×r
   ua_degradation                                        fouling, UA↓
   cool_stuck   cond_stuck                               valve frozen
```

**Stochastic forcing** — Ornstein–Uhlenbeck feed noise so the twin is never
trivially periodic:

```
    dW  =  −θ·W·dt  +  σ·√dt·𝒩(0,1)        θ = OU_THETA, σ = OU_SIGMA_FEED
```

Measurement noise is additive Gaussian per tag class
(`SIGMA_T`, `SIGMA_P`, `SIGMA_FLOW`, `SIGMA_COMP`).

---

## A2.5 Control layer — incremental PID with anti-windup

Every loop in all three models:

```
    e(t)   =  SP − PV(t)

    I(t)   =  I(t−Δt)  +  e(t)·Δt

               e(t) − e(t−Δt)
    D(t)   =  ─────────────────
                     Δt

    u(t)   =  K_p·e(t)  +  K_i·I(t)  +  K_d·D(t)
```

**Anti-windup by integral back-calculation.** On saturation the integral is
rewound by exactly the excess, so the loop leaves saturation the moment the
error reverses instead of unwinding a stored surplus:

```
                       ⎧ I − (u − u_max)/K_i    if u > u_max
    I  ←   ⎨ I − (u − u_min)/K_i    if u < u_min
                       ⎩ I                       otherwise

    u  ←   clamp(u, u_min, u_max)
```

**Bumpless reset.** At steady state `e ≈ 0`, so `u = K_i·I` — the P and D terms
vanish. A naive zero-reset therefore drives `u → 0` and slams every valve shut.
Seeding the integral preserves the holding output:

```
                       u_hold
    I_reset   =   ──────────────
                        K_i
```

Without this, resetting the TEP sim collapsed every controlled flow at once
(separator outlet, compressor recycle, stripper inlet, purge, D-feed) and
tripped a burst of low-flow alarms across three units until the integrators
wound back up.

---

## A2.6 Numerical treatment

| concern | treatment |
|---|---|
| integrator | `solve_ivp`, RK45 adaptive, per 1 s tick |
| stiffness | derivative clipping per state (`±5 °C/s`, `±100 kPa/s`, `±2 %/s`) |
| non-negativity | `C_A ≥ 0`; `T ≥ 250 K` guard keeps Arrhenius finite |
| composition | renormalised `x ← x/Σx` each RHS call when `Σx > 10⁻⁹` |
| state bounds | every state clipped to a physical envelope on unpack |
| division | `max(·, ε)` on every residence time and flow denominator |

The clipping is deliberate: a digital twin driven by operator input and
injected faults must degrade to an implausible-but-bounded state rather than
produce `NaN` and take the alarm pipeline down with it.
