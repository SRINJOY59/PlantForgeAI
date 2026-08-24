---
tag: AT-1101-E
area: Unit 300
equipment_ref: T-501
doc_id: MSC-BBW-U300-XMEAS-38
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-38 (AT-1101-E) — Product: residual E mol% (spec: max 0.3%)

- **Tag:** AT-1101-E
- **Description:** Product: residual E mol% (spec: max 0.3%)
- **Range:** 0–10 mol%
- **Normal Value:** 0.1 mol%
- **Low / Low-Low Alarm:** N/A mol%
- **High / High-High Alarm:** 0.3 / 0.5 mol%
- **Associated Equipment:** T-501
- **Manipulated Handle / Valve:** FV-502

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.t501.at1101e`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
