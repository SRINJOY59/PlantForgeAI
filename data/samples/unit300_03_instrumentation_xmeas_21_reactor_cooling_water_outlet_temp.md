---
tag: TT-102
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMEAS-21
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-21 (TT-102) — Reactor cooling water outlet temp

- **Tag:** TT-102
- **Description:** Reactor cooling water outlet temp
- **Range:** 20–80 °C
- **Normal Value:** 45 °C
- **Low / Low-Low Alarm:** 30 / 25 °C
- **High / High-High Alarm:** 58 / 65 °C
- **Associated Equipment:** R-101
- **Manipulated Handle / Valve:** TV-102

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.r101.tt102`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
