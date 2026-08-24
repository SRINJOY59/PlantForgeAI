---
tag: DCS-NAMING
area: Unit 300
equipment_ref: U-300
doc_id: MSC-BBW-U300-DCS-NAMING
revision: A
source: MSC-BBW-U300-MASTER-001
---

# 10. DCS Tag Naming Convention

Format: `[LOOP-TYPE]-[AREA][SEQUENCE]`

- **Loop-type prefixes:** FT/FIC (flow), TT/TIC (temperature), PT/PIC (pressure), LT/LIC (level), AT/AIC (analyzer), HV (hand/on-off valve), SC (speed control), JT (power)
- **Area codes:** 1xx = Reactor (R-101), 2xx = Condenser (E-201), 3xx = Separator (D-301), 4xx = Compressor (K-401), 5xx = Stripper (T-501), 6xx = Product/Surge (D-601), 9xx = Purge/utility

**Historian convention:** All XMEAS/XMV tags stream to the plant historian at 1 Hz under the naming pattern `unit300.<area>.<tag>` (e.g., `unit300.reactor.tt101`), matching the `plant:telemetry` Redis stream structure.
