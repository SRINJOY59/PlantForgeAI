---
tag: AT-1101-D
area: Unit 300
equipment_ref: T-501
doc_id: MSC-BBW-U300-XMEAS-37
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-37 (AT-1101-D) — Product: residual D mol% (spec: max 0.5%)

- **Tag:** AT-1101-D
- **Description:** Product: residual D mol% (spec: max 0.5%)
- **Range:** 0–10 mol%
- **Normal Value:** 0.2 mol%
- **Low / Low-Low Alarm:** N/A mol%
- **High / High-High Alarm:** 0.5 / 0.8 mol%
- **Associated Equipment:** T-501
- **Manipulated Handle / Valve:** FV-502

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.t501.at1101d`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
