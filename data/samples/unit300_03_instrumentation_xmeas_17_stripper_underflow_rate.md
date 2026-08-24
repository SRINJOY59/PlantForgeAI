---
tag: FT-501
area: Unit 300
equipment_ref: T-501/D-601
doc_id: MSC-BBW-U300-XMEAS-17
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-17 (FT-501) — Stripper underflow / product rate (Stream 11)

- **Tag:** FT-501
- **Description:** Stripper underflow / product rate (Stream 11)
- **Range:** 0–15 kg/s
- **Normal Value:** 10.8 kg/s
- **Low / Low-Low Alarm:** 6 / 4 kg/s
- **High / High-High Alarm:** 13.5 / 14.5 kg/s
- **Associated Equipment:** T-501/D-601
- **Manipulated Handle / Valve:** LV-501

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.t501/d601.ft501`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
