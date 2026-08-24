---
tag: FT-901
area: Unit 300
equipment_ref: K-401
doc_id: MSC-BBW-U300-XMEAS-10
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-10 (FT-901) — Purge flow (Stream 9)

- **Tag:** FT-901
- **Description:** Purge flow (Stream 9)
- **Range:** 0–0.6 kg/s
- **Normal Value:** 0.24 kg/s
- **Low / Low-Low Alarm:** 0.10 / 0.05 kg/s
- **High / High-High Alarm:** 0.40 / 0.50 kg/s
- **Associated Equipment:** K-401
- **Manipulated Handle / Valve:** HV-901

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.k401.ft901`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
