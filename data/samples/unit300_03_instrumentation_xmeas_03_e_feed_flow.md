---
tag: FT-103
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMEAS-03
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-03 (FT-103) — E (VAM) fresh feed flow

- **Tag:** FT-103
- **Description:** E (VAM) fresh feed flow
- **Range:** 0–6.5 kg/s
- **Normal Value:** 4.7 kg/s
- **Low / Low-Low Alarm:** 3.0 / 2.2 kg/s
- **High / High-High Alarm:** 5.8 / 6.1 kg/s
- **Associated Equipment:** R-101
- **Manipulated Handle / Valve:** FV-103

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.r101.ft103`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
