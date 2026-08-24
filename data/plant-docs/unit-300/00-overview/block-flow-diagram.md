---
tag: U300-BFD
area: Unit 300
equipment_ref: U-300
doc_id: MSC-BBW-U300-BFD
revision: A
source: MSC-BBW-U300-MASTER-001
---

# 3. PROCESS BLOCK FLOW & STREAM OVERVIEW

```
  [Fresh A, D, E] + [Recycle C]
               │
               ▼
       ┌───────────────┐
       │     R-101     │ (Reactor)
       └───────┬───────┘
               │ Stream 7 (Off-gas)
               ▼
       ┌───────────────┐
       │     E-201     │ (Condenser)
       └───────┬───────┘
               │
               ▼
       ┌───────────────┐               Stream 5 (Vapor)
       │     D-301     ├───────────────────────────────┐
       └───────┬───────┘                               │
               │ Stream 10 (Liquid)                    ▼
               ▼                               ┌───────────────┐
       ┌───────────────┐                       │     K-401     │ (Recycle Compressor)
       │     T-501     │ (Stripper)            └───────┬───────┘
       └───────┬───────┘                               │
               │ Stream 11 (Resin Product)             ├──► Stream 9 (Purge)
               ▼                                       │
       ┌───────────────┐                               └──► Stream 8 (Recycle Feed)
       │ D-601 / P-601 │
       └───────────────┘
```
