---
tag: SIF-101
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-SIF-101
revision: A
source: MSC-BBW-U300-MASTER-001
---

# SIF-101 — Reactor High-High Temperature Interlock

- **Trigger:** TT-101 ≥ 128 °C (independent SIS transmitter, not XMEAS-09)
- **Action:** Closes all reactor feed valves ([FV-101](../04-final-control-elements/xmv-03-a-feed-valve.md), [FV-102](../04-final-control-elements/xmv-01-d-feed-valve.md), [FV-103](../04-final-control-elements/xmv-02-e-feed-valve.md), [FV-104](../04-final-control-elements/xmv-04-c-feed-valve.md)), opens cooling water valves to 100% ([TV-102](../04-final-control-elements/xmv-10-reactor-cooling-water-valve.md)), initiates emergency depressurization sequence.
- **Rating:** SIL-2, PFDavg target < 1×10⁻².
