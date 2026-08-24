---
tag: LT-501
area: Unit 300
equipment_ref: T-501
doc_id: MSC-BBW-U300-XMEAS-15
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-15 (LT-501) — Stripper level

- **Tag:** LT-501
- **Description:** Stripper level
- **Range:** 0–100 %
- **Normal Value:** 50 %
- **Low / Low-Low Alarm:** 25 / 15 %
- **High / High-High Alarm:** 75 / 88 %
- **Associated Equipment:** T-501
- **Manipulated Handle / Valve:** LV-501

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.t501.lt501`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
