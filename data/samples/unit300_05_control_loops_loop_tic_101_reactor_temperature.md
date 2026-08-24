---
tag: TIC-101
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-LOOP-TIC101
revision: A
source: MSC-BBW-U300-MASTER-001
---

# TIC-101 — Reactor Temperature Control (Most Safety-Critical Loop)

- **PV:** [TT-101 (XMEAS-09)](../03-instrumentation/xmeas-09-reactor-temperature.md)
- **OP:** Cascades to [TV-102 (XMV-10)](../04-final-control-elements/xmv-10-reactor-cooling-water-valve.md) (reactor cooling water flow) as primary handle; secondary trim uses coil vs. jacket split ratio.
- **Type:** PID, cascade master/slave (temperature master → cooling water flow slave)
- **Setpoint:** 120.4 °C
- **Tuning philosophy:** Conservative gain, moderate reset — reactor thermal mass gives significant lag, but the exothermic, temperature-accelerating kinetics mean **runaway risk grows nonlinearly above ~124 °C.**
- **Interlocks:** High-high temperature (128 °C) trips [SIF-101](../06-safety-instrumented-system/sif-101-reactor-high-temp.md).
