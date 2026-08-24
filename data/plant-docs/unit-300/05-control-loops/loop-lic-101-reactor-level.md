---
tag: LIC-101
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-LOOP-LIC101
revision: A
source: MSC-BBW-U300-MASTER-001
governing_clauses:
  - ANSI/ISA-77.40
  - OSHA 1910.119(j)
---

# LIC-101 — Reactor Level Control Loop

### Process Dynamics & Tuning Trap
- **PV:** [LT-101 (XMEAS-08)](../03-instrumentation/xmeas-08-reactor-level.md)
- **OP:** Controls separator underflow demand valve [LV-301 (XMV-07)](../04-final-control-elements/xmv-07-separator-underflow-valve.md).
- **Setpoint:** 65.0%
- **Integrator Dynamics:** Polymer bed level in R-101 is a non-self-regulating (pure integrating) process. Standard PI tuning without derivative action results in severe level oscillations and high-level alarms ([LT-101 High Alarm: 85%](../03-instrumentation/xmeas-08-reactor-level.md)).
