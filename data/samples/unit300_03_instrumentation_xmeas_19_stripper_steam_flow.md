---
tag: FT-502
area: Unit 300
equipment_ref: T-501
doc_id: MSC-BBW-U300-XMEAS-19
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-19 (FT-502) — Stripper steam flow (Stream 13)

- **Tag:** FT-502
- **Description:** Stripper steam flow (Stream 13)
- **Range:** 0–3.0 kg/s
- **Normal Value:** 1.6 kg/s
- **Low / Low-Low Alarm:** 0.7 / 0.4 kg/s
- **High / High-High Alarm:** 2.4 / 2.7 kg/s
- **Associated Equipment:** T-501
- **Manipulated Handle / Valve:** FV-502

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.t501.ft502`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
