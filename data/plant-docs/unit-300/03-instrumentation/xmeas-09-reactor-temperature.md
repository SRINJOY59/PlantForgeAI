---
tag: TT-101
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMEAS-09
revision: A
source: MSC-BBW-U300-MASTER-001
calibration_status: OVERDUE
last_calibrated: 2024-01-10
next_calibration_due: 2025-01-10
---

# XMEAS-09 (TT-101) — Reactor Temperature Transmitter

- **Tag:** TT-101
- **Description:** Reactor Internal Temperature Element & Transmitter
- **Range:** 60.0 to 180.0 °C (Dual Thermocouple Element Type K)
- **Normal Operating Setpoint:** 120.4 °C
- **Alarm Setpoints:** Low: 115.0 °C | Low-Low: 110.0 °C | High: 124.0 °C | High-High: 128.0 °C
- **Calibration Status:** **OVERDUE** (Annual loop calibration due 2025-01-10).
- **Control Cascades:** Primary PV for [TIC-101 Loop](../05-control-loops/loop-tic-101-reactor-temperature.md) controlling cooling water valve [TV-102](../04-final-control-elements/xmv-10-reactor-cooling-water-valve.md).
- **Safety Interlock:** Triggers [SIF-101](../06-safety-instrumented-system/sif-101-reactor-high-temp.md) at High-High threshold (128.0 °C).
