---
tag: D-301
area: Unit 300
equipment_ref: D-301
doc_id: MSC-BBW-U300-EQ-D301
revision: B
source: MSC-BBW-U300-MASTER-001
last_inspection_date: 2022-09-20
next_inspection_due: 2027-09-20
inspection_status: COMPLIANT
---

# D-301 — Vapor-Liquid Separator (Flash Drum)

### 1. Equipment Summary
Vapor-Liquid Separator D-301 receives the partially condensed two-phase stream from Condenser E-201. It flashes off unreacted light gas monomers (Hydrogen, Ethylene, Nitrogen, 1-Butene) overhead to Recycle Compressor K-401 (Stream 5) and collects crude liquid polymer resin at the bottom to feed Stripper T-501 (Stream 10).

- **Type:** Vertical Knockout Flash Vessel with internal 316L SS wire-mesh demister pad.
- **Design Volume:** 34.0 m³
- **Design Pressure / Temp:** 4.30 MPag / 130.0 °C
- **Normal Operating Pressure:** 2.60 MPag ([PT-301](../03-instrumentation/xmeas-13-separator-pressure.md))
- **Normal Operating Level:** 50.0% ([LT-301](../03-instrumentation/xmeas-12-separator-level.md))
- **Shell Material:** SA-516 Grade 70 Carbon Steel with 3.0 mm 304L SS internal cladding.

### 2. Instrumentation & Control Connections
- **Liquid Level Control:** [LIC-301 Loop](../05-control-loops/loop-lic-301-separator-level.md) driving underflow control valve [LV-301 (XMV-07)](../04-final-control-elements/xmv-07-separator-underflow-valve.md).
- **Overpressure Relief:** [PSV-301](../06-safety-instrumented-system/psv-301.md) set at 4.30 MPag discharging to flare header.
