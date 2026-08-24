---
doc_id: PLANTMIND-FAQ-001
area: System Documentation
title: PlantMind Industrial Intelligence Platform — Frequently Asked Questions (FAQ)
revision: A
source: PlantMind Engineering Core
---

# PlantMind (PlantForge.ai) — Frequently Asked Questions (FAQ)

Welcome to the **PlantMind** Knowledge Base & Operations FAQ. This document provides clear, technical, and operational answers regarding the platform architecture, retrieval engine (PathRAG), P&ID digitization, agent collaboration network, safety compliance, and local deployment instructions.

---

## 1. General & Architecture

### Q1.1: What is PlantMind / PlantForge.ai?
**PlantMind** is an industrial intelligence platform and "Unified Asset & Operations Brain" designed for process plants (chemical refineries, manufacturing, power generation). It ingests heterogeneous plant documentation—P&ID schematics, SOPs, work orders, OEM manuals, inspection CSVs, and operator emails—into a unified Neo4j Knowledge Graph. It provides citation-backed Q&A, predictive failure warnings, automated work permit drafting, and hands-free voice co-piloting for field engineers.

### Q1.2: What are the core microservices and ports?
- **Gateway Edge Service (`:8000`)**: Handles CORS, file uploads, citation streaming, rate limiting, and SSE streams.
- **Retrieval Engine (`:8001`)**: Implements semantic search, Local PPR neighborhood search, and **PathRAG** multi-hop path tracing.
- **Agents Service (`:8002` + Celery)**: Houses stateful agents (Field Copilot, MoC, PTW, Investigator, Compliance Scanner).
- **Redis Bus**: Manages queues, locks, delta event streams (`graph:deltas`), and semantic answer caching.
- **Neo4j DB (`:7474` / `:7687`)**: Central graph database store. Writes are strictly routed through the single-writer `graphd` worker service.
- **MinIO Object Store (`:9000` / `:9001`)**: S3-compatible local bucket for raw PDFs, SVGs, and generated PDF reports.

---

## 2. Retrieval Engine & PathRAG

### Q2.1: How does 3-mode retrieval work in PlantMind?
PlantMind routes questions across three distinct retrieval modes based on query intent:
1. **Vector Mode (`vector`)**: Dense Approximate Nearest Neighbor (ANN) search over chunk embeddings for single-fact lookups.
2. **Local Mode (`local`)**: Asset-centric neighborhood extraction using Personalized PageRank (PPR) around target tags (e.g. `P-101A`).
3. **PathRAG Mode (`path`)**: Multi-hop causal graph traversal. It traces physical or logical connections between entities in Neo4j (e.g. `Equipment ──CONNECTED_TO──► Line ──CONNECTED_TO──► Valve`), prunes low-density paths using flow reliability scoring, and presents the exact causal chain of evidence to the LLM.

### Q2.2: How does PlantMind prevent LLM hallucinations?
Every generated answer undergoes a **Grounding Verification Check**:
- **`documents`**: Every tag and claim is explicitly backed by retrieved citations in context (`[doc:id p3]`).
- **`general`**: The model answered from general knowledge (e.g. "What is BARG?"), clearly flagged to the user.
- **`unverified`**: If the model fabricated a citation or tag not present in retrieved context, the claim is flagged as unverified and rejected from trusted status.

---

## 3. P&ID Digitization Pipeline

### Q3.1: How does PlantMind digitize Piping & Instrumentation Diagrams (P&IDs)?
PlantMind uses a **hybrid deterministic-semantic pipeline**:
1. **Pyramidal OpenCV Tiling**: Slices high-DPI P&ID schematics into overlapping tiles with a 20% spatial margin to prevent line severance.
2. **Deterministic Bounding Box Extraction**: Uses `PyMuPDF` (`fitz`) on vector PDFs to extract text labels and exact `(x0, y0, x1, y1)` bounding boxes directly from vector layers.
3. **Two-Pass VLM Line Tracing**: Passes high-res tiles along with spatial tag anchors to a Vision Language Model (VLM) to follow line segments, extract flow directions (`forward`, `bidirectional`), and stitch tile edges into a global coordinate map.

---

## 4. Agent Collaboration & Usecases

### Q4.1: What is the `AgentBroker` collaboration model?
The `AgentBroker` is a mediator pattern that enables specialized usecase agents to share capabilities dynamically without tight coupling or circular dependencies:
- **`InvestigatorAgent`**: Analyzes historical failure modes and root causes.
- **`ComplianceScanner`**: Queries statutory inspection dates (API 510/570/526) and identifies overdue equipment.
- **`PermitToWorkAgent (PTW)`**: Requests overdue compliance flags from `ComplianceScanner` via `AgentBroker` to inject them as high-priority safety hazards in work permits.
- **`ChangeImpact (MoC)`**: Requests compliance flags to inject `[COMPLIANCE ALERT]` governing clauses in Management of Change reviews.
- **`ReportGeneratorAgent`**: Appends overdue inspection warning tables to generated PDF asset reports.
- **`FieldCopilotAgent`**: Requests both compliance flags and failure histories to speak an automated safety briefing to field technicians at session start.

---

## 5. Field Copilot & Hands-Free SOP Execution

### Q5.1: How does Field Copilot work for field technicians wearing PPE?
Field Copilot is a stateful, voice-guided assistant designed for rugged tablet or headset use in hazardous environments:
- **Local STT / TTS**: Uses the browser's native **Web Speech API** for instant speech-to-text and text-to-speech without external API latency.
- **Stateful Redis Caching**: SOP steps are cached in Redis per session. Operators can say *"Next step"*, *"Repeat"*, or *"Read hazard"*.
- **Pre-filled Safety Briefings**: Pre-loads overdue inspection warnings and past failure modes into the spoken introduction before step 1.

---

## 6. Running & Ingestion Instructions

### Q6.1: How do I ingest sample data and build the Knowledge Graph?
Run the following command from the project root:
```bash
python -m tools.build_kg data/samples
```
This submits all 212+ sample files (CSV work orders, inspection records, SVG P&IDs, markdown equipment sheets, LOTO procedures, HAZOP reports) to Redis queues, drains the Celery extraction workers, and populates Neo4j.

### Q6.2: How do I run the offline evaluation test suite?
Run:
```bash
python -m pytest -q
```
All ~190 tests run offline using `fakeredis` and test mocks.

To run the golden QA evaluation harness:
```bash
python -m eval.run_eval
```
