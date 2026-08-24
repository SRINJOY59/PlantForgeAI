---
tag: FT-101
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMEAS-01
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-01 (FT-101) — A (Hydrogen) fresh feed flow

- **Tag:** FT-101
- **Description:** A (Hydrogen) fresh feed flow
- **Range:** 0–0.6 kg/s
- **Normal Value:** 0.32 kg/s
- **Low / Low-Low Alarm:** 0.15 / 0.10 kg/s
- **High / High-High Alarm:** 0.50 / 0.55 kg/s
- **Associated Equipment:** R-101
- **Manipulated Handle / Valve:** FV-101

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.r101.ft101`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
