---
tag: FT-301
area: Unit 300
equipment_ref: D-301/T-501
doc_id: MSC-BBW-U300-XMEAS-14
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-14 (FT-301) — Separator underflow to stripper (Stream 10)

- **Tag:** FT-301
- **Description:** Separator underflow to stripper (Stream 10)
- **Range:** 0–24 kg/s
- **Normal Value:** 16.8 kg/s
- **Low / Low-Low Alarm:** 10 / 6 kg/s
- **High / High-High Alarm:** 20 / 22 kg/s
- **Associated Equipment:** D-301/T-501
- **Manipulated Handle / Valve:** LV-301

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.d301/t501.ft301`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
