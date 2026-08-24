---
tag: HISTORIAN-ARCH
area: Unit 300
equipment_ref: U-300
doc_id: MSC-BBW-U300-HISTORIAN-ARCH
revision: A
source: MSC-BBW-U300-MASTER-001
---

# 10.1 Historian Architecture

Historian retains 1 Hz raw data for 90 days, 1-minute averages for 3 years, hourly averages indefinitely. All 41 XMEAS + 12 XMV tags plus derived/calculated tags (e.g., surge margin, product yield) are historized. Composition analyzer tags (XMEAS-23 through 41) are historized at their native GC cycle time, not upsampled.
