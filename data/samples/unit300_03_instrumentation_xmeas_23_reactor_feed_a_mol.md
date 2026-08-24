---
tag: AT-601-A
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMEAS-23
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-23 (AT-601-A) — Reactor feed: A (H2) mol%

- **Tag:** AT-601-A
- **Description:** Reactor feed: A (H2) mol%
- **Range:** 0–100 mol%
- **Normal Value:** 0.5 mol%
- **Low / Low-Low Alarm:** N/A mol%
- **High / High-High Alarm:** N/A mol%
- **Associated Equipment:** R-101
- **Manipulated Handle / Valve:** FV-101

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.r101.at601a`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
