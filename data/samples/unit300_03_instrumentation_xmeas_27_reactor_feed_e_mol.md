---
tag: AT-601-E
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMEAS-27
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-27 (AT-601-E) — Reactor feed: E (VAM) mol%

- **Tag:** AT-601-E
- **Description:** Reactor feed: E (VAM) mol%
- **Range:** 0–100 mol%
- **Normal Value:** 20.0 mol%
- **Low / Low-Low Alarm:** N/A mol%
- **High / High-High Alarm:** N/A mol%
- **Associated Equipment:** R-101
- **Manipulated Handle / Valve:** FV-103

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.r101.at601e`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
