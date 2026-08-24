---
tag: AT-601-F
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMEAS-28
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-28 (AT-601-F) — Reactor feed: F (byproduct) mol%

- **Tag:** AT-601-F
- **Description:** Reactor feed: F (byproduct) mol%
- **Range:** 0–100 mol%
- **Normal Value:** 1.0 mol%
- **Low / Low-Low Alarm:** N/A mol%
- **High / High-High Alarm:** N/A mol%
- **Associated Equipment:** R-101
- **Manipulated Handle / Valve:** N/A

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.r101.at601f`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
