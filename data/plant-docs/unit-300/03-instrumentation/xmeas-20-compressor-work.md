---
tag: JT-401
area: Unit 300
equipment_ref: K-401
doc_id: MSC-BBW-U300-XMEAS-20
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-20 (JT-401) — Compressor work (power)

- **Tag:** JT-401
- **Description:** Compressor work (power)
- **Range:** 0–4000 kW
- **Normal Value:** 2650 kW
- **Low / Low-Low Alarm:** 1500 / 1000 kW
- **High / High-High Alarm:** 3400 / 3700 kW
- **Associated Equipment:** K-401
- **Manipulated Handle / Valve:** HV-401

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.k401.jt401`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
