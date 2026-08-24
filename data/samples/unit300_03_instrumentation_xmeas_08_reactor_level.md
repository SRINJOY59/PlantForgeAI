---
tag: LT-101
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMEAS-08
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-08 (LT-101) — Reactor level

- **Tag:** LT-101
- **Description:** Reactor level
- **Range:** 0–100 %
- **Normal Value:** 65 %
- **Low / Low-Low Alarm:** 40 / 25 %
- **High / High-High Alarm:** 85 / 92 %
- **Associated Equipment:** R-101
- **Manipulated Handle / Valve:** LV-301

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.r101.lt101`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
