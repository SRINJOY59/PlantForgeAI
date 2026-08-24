---
tag: FT-102
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMEAS-02
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-02 (FT-102) — D (1-Butene) fresh feed flow

- **Tag:** FT-102
- **Description:** D (1-Butene) fresh feed flow
- **Range:** 0–6.0 kg/s
- **Normal Value:** 4.0 kg/s
- **Low / Low-Low Alarm:** 2.5 / 1.8 kg/s
- **High / High-High Alarm:** 5.2 / 5.6 kg/s
- **Associated Equipment:** R-101
- **Manipulated Handle / Valve:** FV-102

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.r101.ft102`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
