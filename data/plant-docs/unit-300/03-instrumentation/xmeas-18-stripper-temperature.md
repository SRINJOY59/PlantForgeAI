---
tag: TT-501
area: Unit 300
equipment_ref: T-501
doc_id: MSC-BBW-U300-XMEAS-18
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-18 (TT-501) — Stripper temperature

- **Tag:** TT-501
- **Description:** Stripper temperature
- **Range:** 30–110 °C
- **Normal Value:** 65.0 °C
- **Low / Low-Low Alarm:** 55 / 48 °C
- **High / High-High Alarm:** 72 / 78 °C
- **Associated Equipment:** T-501
- **Manipulated Handle / Valve:** FV-502

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.t501.tt501`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
