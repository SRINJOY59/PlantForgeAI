---
tag: AT-601-D
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMEAS-26
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-26 (AT-601-D) — Reactor feed: D (1-butene) mol%

- **Tag:** AT-601-D
- **Description:** Reactor feed: D (1-butene) mol%
- **Range:** 0–100 mol%
- **Normal Value:** 18.5 mol%
- **Low / Low-Low Alarm:** N/A mol%
- **High / High-High Alarm:** N/A mol%
- **Associated Equipment:** R-101
- **Manipulated Handle / Valve:** FV-102

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.r101.at601d`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
