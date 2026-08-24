---
tag: TT-201
area: Unit 300
equipment_ref: E-201
doc_id: MSC-BBW-U300-XMEAS-22
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-22 (TT-201) — Condenser cooling water outlet temp

- **Tag:** TT-201
- **Description:** Condenser cooling water outlet temp
- **Range:** 20–80 °C
- **Normal Value:** 42 °C
- **Low / Low-Low Alarm:** 30 / 25 °C
- **High / High-High Alarm:** 55 / 62 °C
- **Associated Equipment:** E-201
- **Manipulated Handle / Valve:** TV-201

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.e201.tt201`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
