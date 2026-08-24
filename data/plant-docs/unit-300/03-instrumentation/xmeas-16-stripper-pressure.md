---
tag: PT-501
area: Unit 300
equipment_ref: T-501
doc_id: MSC-BBW-U300-XMEAS-16
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-16 (PT-501) — Stripper pressure

- **Tag:** PT-501
- **Description:** Stripper pressure
- **Range:** 0–2.5 MPag
- **Normal Value:** 1.08 MPag
- **Low / Low-Low Alarm:** 0.85 / 0.70 MPag
- **High / High-High Alarm:** 1.30 / 1.45 MPag
- **Associated Equipment:** T-501
- **Manipulated Handle / Valve:** FV-502

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.t501.pt501`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
