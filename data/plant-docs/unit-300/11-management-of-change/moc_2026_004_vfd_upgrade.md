---
doc_id: MOC-2026-004
tag: MOC-2026-004
area: Unit 300
equipment_ref: R-101
proposed_by: S. Patel
governing_clauses:
  - OSHA 29 CFR 1910.119(l) Management of Change
---

# Management of Change (MOC-2026-004): R-101 Agitator VFD Upgrade

### 1. Proposal Summary
Upgrade the existing VFD drive controller for [R-101 Agitator SC-101](../04-final-control-elements/xmv-12-reactor-agitator-speed.md) from legacy analog drive to ABB ACS880 Industrial Drive with integrated Safe Torque Off (STO) capability.

### 2. Affected System Components
- **Equipment:** [R-101 Reactor](../02-equipment/r-101-reactor.md)
- **Control Loop:** [SC-101 Loop](../05-control-loops/loop-sc-101-agitator-speed.md)
- **Documents to Revise:** [SOP-300-01 Startup](../09-procedures/sop-startup.md), [SOP-300-05 LOTO](../09-procedures/sop-loto-reactor.md), Electrical Wiring Diagram MSC-BBW-E-401.

### 3. Safety Impact Assessment
The STO feature provides SIL-3 electrical isolation, eliminating the requirement to rack out the 480V breaker for brief mechanical seal inspections.
