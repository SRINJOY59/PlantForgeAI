---
tag: PT-101
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMEAS-07
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-07 (PT-101) — Reactor pressure

- **Tag:** PT-101
- **Description:** Reactor pressure
- **Range:** 0–5.0 MPag
- **Normal Value:** 2.80 MPag
- **Low / Low-Low Alarm:** 2.4 / 2.2 MPag
- **High / High-High Alarm:** 3.1 / 3.3 MPag
- **Associated Equipment:** R-101
- **Manipulated Handle / Valve:** HV-901

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.r101.pt101`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
