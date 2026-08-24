---
tag: HV-901
area: Unit 300
equipment_ref: K-401
doc_id: MSC-BBW-U300-XMV-06
revision: B
source: MSC-BBW-U300-MASTER-001
last_inspection_date: 2024-01-20
next_inspection_due: 2026-01-20
inspection_status: OVERDUE
---

# XMV-06 (HV-901) — Reactor Loop Inert Purge Control Valve

### 1. Technical & Actuator Specifications
- **Tag:** HV-901 (DCS Output: XMV-06)
- **Valve Type:** 2-inch Globe Valve, 316L SS Body, Stellite trim, Class 600.
- **Actuator Type:** Pneumatic Spring-Diaphragm with HART digital positioner.
- **Fail Position:** Fail Closed (FC) — Prevents emergency venting of flammable recycle gas on loss of air.
- **Normal Operating Position:** 40% Open (Modulates between 15% and 85%).
- **Associated Equipment:** [K-401 Compressor](../02-equipment/k-401-recycle-compressor.md) & [R-101 Reactor](../02-equipment/r-101-reactor.md).
- **Associated Process Measurements:** [FT-901 (Purge Flow)](../03-instrumentation/xmeas-10-purge-flow.md), [PT-101 (Reactor Pressure)](../03-instrumentation/xmeas-07-reactor-pressure.md), [AT-901-B (Inert N2 mol%)](../03-instrumentation/xmeas-30-purge-b-mol.md).

### 2. Control System Role & Process Interactions
HV-901 is a critical dual-function control valve:
1. **Inert (Nitrogen) Bleed:** Continuous removal of non-reactive Nitrogen gas (Stream 9) that enters with feed streams to prevent buildup in the gas recycle loop.
2. **Reactor Pressure Trim:** Works in split-range configuration with [PIC-101 Loop](../05-control-loops/loop-pic-101-reactor-pressure.md). When reactor pressure rises above 2.85 MPag, HV-901 opens further to dump gas to the site fuel gas header.

### 3. Maintenance & Maintenance Status
- **Inspection Status:** **OVERDUE** for packing gland repacking and digital positioner calibration (Due: 2026-01-20).
- **Known Failure Upset:** Nitrogen accumulation in recycle loop when HV-901 sticks closed ([IDV-02](../07-disturbance-library/idv-02.md)).
