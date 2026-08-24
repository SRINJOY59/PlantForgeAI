---
tag: FV-102
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-XMV-01
revision: B
source: MSC-BBW-U300-MASTER-001
---

# XMV-01 (FV-102) — 1-Butene Fresh Feed Control Valve

- **Tag:** FV-102 (DCS Output: XMV-01)
- **Description:** 3-inch Fisher Globe Valve controlling 1-Butene (Stream 2) fresh feed to R-101.
- **Fail Position:** Fail Closed (FC). Normal position: 62% Open.
- **Control Cascades:** Manipulated by ratio controller [FFC-102/103](../05-control-loops/loop-ratio-de-feed.md) to set MSC-6200 product grade.
- **Safety Interlocks:** Tripped closed by [SIF-101](../06-safety-instrumented-system/sif-101-reactor-high-temp.md) and [SIF-102](../06-safety-instrumented-system/sif-102-reactor-high-pressure.md).
