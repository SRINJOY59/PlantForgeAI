---
tag: FT-104
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMEAS-04
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-04 (FT-104) — C (Ethylene) combined feed flow

- **Tag:** FT-104
- **Description:** C (Ethylene) combined feed flow
- **Range:** 0–20 kg/s
- **Normal Value:** 11.2 kg/s
- **Low / Low-Low Alarm:** 7.0 / 5.0 kg/s
- **High / High-High Alarm:** 16.0 / 18.0 kg/s
- **Associated Equipment:** R-101
- **Manipulated Handle / Valve:** FV-104

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.r101.ft104`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
