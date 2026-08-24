---
tag: PT-301
area: Unit 300
equipment_ref: D-301
doc_id: MSC-BBW-U300-XMEAS-13
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-13 (PT-301) — Separator pressure

- **Tag:** PT-301
- **Description:** Separator pressure
- **Range:** 0–4.5 MPag
- **Normal Value:** 2.60 MPag
- **Low / Low-Low Alarm:** 2.2 / 2.0 MPag
- **High / High-High Alarm:** 2.9 / 3.1 MPag
- **Associated Equipment:** D-301
- **Manipulated Handle / Valve:** HV-401

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.d301.pt301`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
