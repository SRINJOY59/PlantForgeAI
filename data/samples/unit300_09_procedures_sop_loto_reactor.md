---
tag: SOP-300-05
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-SOP-05
revision: A
source: MSC-BBW-U300-MASTER-001
governing_regulations:
  - OSHA 29 CFR 1910.147 (Control of Hazardous Energy)
  - OSHA 29 CFR 1910.119(f)
required_ppe:
  - Level B Chemical Suit
  - SCBA (Self-Contained Breathing Apparatus)
  - Nitrile Chemical Gloves
  - Safety Goggles & Hard Hat
isolation_points:
  - FV-101 (Hydrogen Line Block)
  - FV-102 (1-Butene Line Block)
  - FV-103 (VAM Line Block)
  - FV-104 (Ethylene Line Block)
  - MCC Breaker #B-301 (SC-101 Agitator)
---

# SOP-300-05 — Lockout / Tagout (LOTO) & Safe Entry Procedure: R-101 Reactor

### 1. Purpose & Scope
Establishes mandatory energy isolation and vessel entry procedures for maintenance, internal inspection, or catalyst cleanout on Reactor [R-101](../02-equipment/r-101-reactor.md). Complies strictly with OSHA 1910.147 and PSM guidelines.

### 2. Hazardous Energy & Chemical Isolation Checklist
1. **Hydrogen Feed Isolation:** Close manual block valve upstream of [FV-101](../04-final-control-elements/xmv-03-a-feed-valve.md), install lock and red tag #LOTO-101A.
2. **1-Butene Feed Isolation:** Close manual block valve upstream of [FV-102](../04-final-control-elements/xmv-01-d-feed-valve.md), install lock and red tag #LOTO-102A.
3. **VAM Feed Isolation:** Close manual block valve upstream of [FV-103](../04-final-control-elements/xmv-02-e-feed-valve.md), install lock and red tag #LOTO-103A.
4. **Ethylene Feed Isolation:** Close manual block valve upstream of [FV-104](../04-final-control-elements/xmv-04-c-feed-valve.md), install lock and red tag #LOTO-104A.
5. **Electrical Power Isolation:** Open and lock out MCC 480V Breaker #B-301 feeding the 150 kW agitator motor ([SC-101](../04-final-control-elements/xmv-12-reactor-agitator-speed.md)). Apply lock and tag #LOTO-ELE-301.

### 3. Depressurization & Nitrogen Purge Protocol
1. Depressurize R-101 to flare header via manual vent line until [PT-101](../03-instrumentation/xmeas-07-reactor-pressure.md) reads 0.00 MPag.
2. Connect utility N2 purge line and flush reactor volume with 5 system volume changes of dry nitrogen until gas analyzer reads hydrocarbon < 0.1% LEL.
3. Perform Sniff Test for toxic VAM monomer ([AT-601-E](../03-instrumentation/xmeas-27-reactor-feed-e-mol.md)). Ensure O2 level reads 20.9% before issuing Confined Space Entry Permit.
