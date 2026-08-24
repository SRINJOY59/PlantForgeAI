---
tag: TT-301
area: Unit 300
equipment_ref: D-301
doc_id: MSC-BBW-U300-XMEAS-11
revision: A
source: MSC-BBW-U300-MASTER-001
---

# XMEAS-11 (TT-301) — Separator temperature

- **Tag:** TT-301
- **Description:** Separator temperature
- **Range:** 40–140 °C
- **Normal Value:** 82.5 °C
- **Low / Low-Low Alarm:** 70 / 60 °C
- **High / High-High Alarm:** 92 / 98 °C
- **Associated Equipment:** D-301
- **Manipulated Handle / Valve:** TV-201

### Function & Process Role
This measurement streams to the plant historian at 1 Hz under `unit300.d301.tt301`. It is utilized by the DCS control loops and monitored by the PlantForge anomaly detector for real-time fault diagnosis.
