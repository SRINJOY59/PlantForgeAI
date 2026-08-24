---
tag: LT-301
area: Unit 300
equipment_ref: D-301
doc_id: MSC-BBW-U300-XMEAS-12
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-12 (LT-301) — Separator level

- **Tag:** LT-301
- **Description:** Separator level
- **Range:** 0–100 %
- **Normal Value:** 50 %
- **Low / Low-Low Alarm:** 25 / 15 %
- **High / High-High Alarm:** 75 / 88 %
- **Associated Equipment:** D-301
- **Manipulated Handle / Valve:** LV-301

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.d301.lt301`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
