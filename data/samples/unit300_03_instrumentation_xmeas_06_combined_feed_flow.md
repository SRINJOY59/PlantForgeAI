---
tag: FT-106
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMEAS-06
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-06 (FT-106) — Combined reactor feed flow (Stream 6)

- **Tag:** FT-106
- **Description:** Combined reactor feed flow (Stream 6)
- **Range:** 0–75 kg/s
- **Normal Value:** 49.0 kg/s
- **Low / Low-Low Alarm:** 35 / 25 kg/s
- **High / High-High Alarm:** 62 / 68 kg/s
- **Associated Equipment:** R-101
- **Manipulated Handle / Valve:** FV-101..104

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.r101.ft106`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
