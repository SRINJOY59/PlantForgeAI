---
tag: AT-601-B
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMEAS-24
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-24 (AT-601-B) — Reactor feed: B (N2, inert) mol%

- **Tag:** AT-601-B
- **Description:** Reactor feed: B (N2, inert) mol%
- **Range:** 0–100 mol%
- **Normal Value:** 12.0 mol%
- **Low / Low-Low Alarm:** N/A mol%
- **High / High-High Alarm:** N/A mol%
- **Associated Equipment:** R-101
- **Manipulated Handle / Valve:** HV-901

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.r101.at601b`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
