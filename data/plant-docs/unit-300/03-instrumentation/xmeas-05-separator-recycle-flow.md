---
tag: FT-105
area: Unit 300
equipment_ref: D-301/K-401
doc_id: MSC-BBW-U300-XMEAS-05
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-05 (FT-105) — Separator-to-compressor recycle flow (Stream 5)

- **Tag:** FT-105
- **Description:** Separator-to-compressor recycle flow (Stream 5)
- **Range:** 0–60 kg/s
- **Normal Value:** 38.5 kg/s
- **Low / Low-Low Alarm:** 25 / 18 kg/s
- **High / High-High Alarm:** 50 / 55 kg/s
- **Associated Equipment:** D-301/K-401
- **Manipulated Handle / Valve:** HV-401

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.d301/k401.ft105`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
