---
doc_id: IR-2026-014
equipment_ref: R-101
unit: Unit 300
date: 2026-01-14
severity: WARNING
---

# Incident Report IR-2026-014: Reactor R-101 Thermal Excursion & TV-102 Valve Binding

### Event Overview
On 2026-01-14 at 14:22 CST, Reactor [R-101](unit300_02_equipment_r_101_reactor.md) temperature ([TT-101](unit300_03_instrumentation_xmeas_09_reactor_temperature.md)) experienced a rapid thermal excursion from normal setpoint 120.4 °C up to 126.8 °C (0.4 °C below the [SIF-101](unit300_06_safety_instrumented_system_sif_101_reactor_high_temp.md) emergency trip threshold of 128.0 °C).

### Root Cause Analysis (RCA)
- **Primary Cause:** Mechanical binding of positioner feedback linkage on reactor jacket cooling water valve [TV-102](unit300_04_final_control_elements_xmv_10_reactor_cooling-water_valve.md) (IDV-14 fault).
- **Secondary Factor:** Delayed operator notification due to ISA-18.2 alarm debounce.

### Corrective Actions
1. Emergency stroke test performed on TV-102 under Work Order [WO-5014](work_orders_unit300.csv).
2. Positioner feedback arm replaced and re-calibrated.
3. Updated PM schedule to mandate bi-monthly stroke testing under [SOP-300-05](unit300_09_procedures_sop_loto_reactor.md).