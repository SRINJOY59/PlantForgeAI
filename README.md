<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="ui/src/assets/logo-dark.png">
    <img src="ui/src/assets/logo-light.png" alt="PlantForge.ai" width="140">
  </picture>
</p>

<h1 align="center">PlantForge.ai</h1>
<p align="center"><em>Enterprise Industrial Knowledge Intelligence &amp; Operational AI Co-Pilot for Process Plants</em></p>

<p align="center">
  <img alt="stack" src="https://img.shields.io/badge/stack-Docker%20Compose-2496ED">
  <img alt="llm" src="https://img.shields.io/badge/LLM-Vertex%20AI%20%7C%20OpenRouter-4285F4">
  <img alt="graph" src="https://img.shields.io/badge/graph-Neo4j%205-008CC1">
  <img alt="timeseries" src="https://img.shields.io/badge/historian-TimescaleDB-FDB515">
  <img alt="simulation" src="https://img.shields.io/badge/simulation-Tennessee%20Eastman-blue">
  <img alt="slack" src="https://img.shields.io/badge/notifications-Slack%20Enterprise-4A154B">
  <img alt="tests" src="https://img.shields.io/badge/tests-405%20passing-16a34a">
</p>

---

## Overview

**PlantForge** transforms unstructured plant documentation (P&IDs, maintenance work orders, SOPs, OEM manuals, laboratory logs, and statutory inspection certificates) and high-frequency time-series telemetry into an active, unified **Industrial Knowledge Brain**. Combining multi-modal graph retrieval (**PathRAG**), a high-performance **TimescaleDB Historian**, live **Tennessee Eastman Process (TEP)** simulation, and persona-tailored reasoning, PlantForge enables real-time root-cause analysis, predictive failure detection, statutory compliance tracking, and voice-assisted field operations.

Built for **ET AI Hackathon 2026, PS-8** (*Unified Asset & Operations Brain*).

---

## Key Capabilities

| Capability | Technical Mechanism |
|---|---|
| **Multi-Persona AI Reasoning** | Dynamic prompt grounding and token budgets tailored for **Field Operator** (checklists/limits), **Process Engineer** (kinetics/control loops), **Maintenance Lead** (CMMS/work orders), and **Safety Officer** (OISD/IBR standards). |
| **PathRAG & Hybrid Graph Retrieval** | 3-mode retrieval engine combining vector search, asset-centric local subgraphs, and **causal PathRAG** topology traversals with exact document provenance `[doc:id p3]`. |
| **TimescaleDB Plant Historian** | High-throughput continuous telemetry sink landing sub-second sensor streams into partitioned hypertables with native columnar compression and automated retention. |
| **Statutory Compliance & Standards Center** | Real-time monitoring of regulatory obligations (**OISD-STD-119**, **IBR/OISD-STD-132**, **API 510/570/653**) directly from the graph with 1-click **PM02 work order drafting**. |
| **Enterprise Slack Alerts** | Automated webhook dispatcher broadcasting rich block-formatted statutory inspection alerts and AI failure diagnoses with actionable remediation links. |
| **Dynamic Failure Pattern Detection** | Continuous graph analysis of equipment failure modes (`HAS_FAILURE`) and CMMS logs (`WorkOrder`) surfacing recurring root causes (e.g. `P-101A` cavitation & `PI-102` low suction pressure). |
| **Real-Time Physics Simulation (TEP / CSTR)** | Live dynamic simulation of the **Tennessee Eastman Process** (8 chemical species, 4 gas reactions, 12 PID loops, 21 IDV fault injections) and ISA 18.2 alarm envelopes. |
| **Automated AI Root-Cause Investigation** | Multi-agent diagnostic runtime triggered on process limit breaches that evaluates sensor signatures, isolates root causes, and pre-fills the answer cache. |
| **Mobile Field Co-Pilot (PWA) & Voice** | Mobile-first interface with multilingual audio synthesis (`hi`, `bn`, `ta`, `te`, `mr`, `gu`), voice dictation, and barcode/tag scanning for field walkdowns. |
| **Live Document Reader** | Integrated viewer rendering Markdown, CSV, tabular inspection records, and PDFs directly from MinIO object storage with provenance highlights. |
| **MCP Server Integration** | Exposes 9 Model Context Protocol (MCP) tools over stdio for external AI assistants to query plant graph topology and telemetry. |

---

## TimescaleDB Industrial Historian Architecture

PlantForge features an enterprise-grade time-series telemetry engine built on **TimescaleDB** designed for high-frequency sensor capture, real-time downsampling, and long-term trend analysis:

```
  Live Plant Telemetry / TEP Simulator
                 │
                 ▼  sub-second sensor batches (JSON)
           Redis Stream (`plant:telemetry`)
                 │
                 ▼  XREADGROUP consumer (`historian-sink-1`)
        Telemetry Sink (`services/historian/sink.py`)
                 │
                 ▼  PostgreSQL bulk `COPY` (at-least-once)
  ┌─────────────────────────────────────────────────────────────┐
  │                    TimescaleDB Engine                       │
  │                                                             │
  │  1. Hypertable Partitioning: (time, tag_id)                 │
  │  2. Columnar Compression: segmentby 'tag_id', orderby 'time'│
  │     (Up to 90-95% storage reduction)                        │
  │  3. Window Aggregations: Dynamic min/max/avg downsampling   │
  │  4. Automated Retention: 90-day sliding data lifecycle      │
  └─────────────────────────────────────────────────────────────┘
                 │
                 ├─► Real-Time Multi-Tag Trend Dashboards
                 ├─► Phase-Space Trajectory & ISA 18.2 Envelopes
                 └─► Historical Upset Signature Mining (Fault Library)
```

### Key Historian Features
* **Hypertable Time-Partitioning**: Telemetry samples are automatically partitioned into time-based chunks, maintaining sub-millisecond query performance across billions of data points.
* **Segmented Columnar Compression**: Automatically compresses older chunks grouped by `tag_id` and ordered by `time DESC`, slashing disk usage by **up to 95%** while keeping compressed data directly queryable via SQL.
* **Zero-Data-Loss Ingestion**: The `historian.sink` background worker batches stream events and issues transactional `COPY` operations before acknowledging messages (`XACK`), guaranteeing at-least-once delivery.
* **Adaptive Backend**: Seamlessly connects to **Timescale Cloud** or self-hosted TimescaleDB, and automatically falls back to standard PostgreSQL tables when running in minimal environments.
* **Fault Library Builder**: The diagnostic engine queries historical time-series baselines to extract multi-variate statistical excursion profiles during equipment trips.

---

## Architecture

```
                       ┌────────────── UI (React + Vite + PWA) ─────────────┐
                       │  Ask · Graph · Alerts · Work Orders · Compliance   │
                       │  TEP Simulation · MOC · Field Co-Pilot · Permits   │
                       └────────────────────────┬───────────────────────────┘
                                                │  HTTP + WebSocket / SSE
                                        ┌───────▼────────┐        ┌─────────────┐
                                        │  gateway :8000 │◄───────┤ MCP server  │
                                        │  FastAPI edge  │        │ (stdio)     │
                                        └───────┬────────┘        └─────────────┘
                        ┌───────────────────────┼──────────────────────┬──────────────────────┐
                        │                       │                      │                      │
                ┌───────▼──────┐        ┌───────▼───────┐      ┌───────▼──────┐       ┌───────▼──────┐
                │ retrieval    │        │ Redis         │      │ MinIO        │       │ TimescaleDB  │
                │ :8001        │        │ telemetry bus │      │ raw documents│       │ hypertable   │
                │ PathRAG      │        │ cache · locks │      └──────────────┘       │ historian    │
                └───────┬──────┘        └───────┬───────┘                             └───────▲──────┘
                        │                       │  celery queues                              │
                        │        ┌──────────────┴───────────────────────┐                     │ COPY
                        │   ingestion → extraction (6 lanes) → resolution → graphd            │ sink
                        │        │                                          │                 │
                        └────────┴──────────► Neo4j (the graph) ◄───────────┴─────────► telemetry-sink
                                                    ▲
                                              agents runtime & watchers
                                              (tep-watcher · delta handler
                                               → investigate → slack alert
                                               → draft work order)
```

### Architectural Guardrails

1. **Single Graph Writer (`graphd`)**: All writes to Neo4j execute through `graphd` via batched `UNWIND` transactions to guarantee deterministic graph versioning.
2. **Durable Time-Series Ingestion**: Telemetry is streamed to Redis and persisted durably into **TimescaleDB** hypertables.
3. **Provenance Preservation**: Every entity and edge stores `(doc_id, page/span, extractor_version, confidence, source)`.
4. **Multi-Tier Model Client**: Primary execution on Vertex AI / high-throughput LLM endpoints with structured schema outputs and OpenRouter fallbacks.
5. **Asynchronous Decoupling**: All inter-service pipelines and telemetry streaming operate over Redis streams and Celery message brokers.

---

## Prerequisites

- **Docker Desktop** (running)
- **Python 3.11+**
- **Node 18+**
- Cloud Vertex AI credentials / API Keys (OpenRouter / OpenAI / Anthropic)

---

## Environment Setup

### 1. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env`:

```ini
# Cloud Vertex AI / LLM Configuration
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1

# TimescaleDB / Industrial Historian (Optional - connects to Timescale Cloud / PostgreSQL)
TIMESCALE_DSN=postgres://user:password@timescale-host:5432/plantmind

# Slack Enterprise Webhook (Optional for live alert broadcasts)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00/B00/XXXX

# Fallback OpenRouter API Key (Optional)
OPENROUTER_API_KEY=sk-or-v1-...
```

### 2. Cloud Vertex AI Authentication

Authenticate your local environment with Application Default Credentials (ADC):

```bash
gcloud auth application-default login
```

### 3. Frontend Setup

```bash
cd ui
npm install
cp .env.example .env      # VITE_GATEWAY_URL=http://localhost:8000
```

---

## Running the Application

### Option A — Full Stack Docker Compose (Recommended)

```bash
docker compose up --build
```

Starts all database and application services:
- **`plantmind-neo4j`**: Knowledge graph database on `:7474` / `:7687`
- **`plantmind-redis`**: Event bus, alert streams, and cache on `:6379`
- **`plantmind-minio`**: Object storage on `:9000` (Console `:9001`)
- **`plantmind-gateway`**: Edge API on `:8000`
- **`plantmind-retrieval`**: PathRAG engine on `:8001`
- **`plantmind-agents-api` / `agents`**: Multi-agent diagnostic runtime
- **`tep-sim` / `tep-watcher`**: Physics simulation & threshold watchers

### Option B — Local Development Mode

Infra in Docker, Python services running locally for instant hot-reloading:

```bash
python -m tools.serve
```

Then start the React UI:

```bash
cd ui
npm run dev        # http://localhost:5173
```

---

## Service Endpoints Map

| Service | Port / URL | Description |
|---|---|---|
| **Web UI** | `http://localhost:5173` | Unified Operations, Compliance & Simulation Dashboard |
| **Gateway API** | `http://localhost:8000` | REST API, SSE Alert Stream, Slack Webhook Proxy |
| **Retrieval Engine** | `http://localhost:8001` | PathRAG, Vector & Local Hybrid Search Service |
| **TEP Physics Simulator** | `http://localhost:8012` | Tennessee Eastman Process simulation engine |
| **Neo4j Browser** | `http://localhost:7474` | Cypher query console (`neo4j` / `password`) |
| **MinIO Console** | `http://localhost:9001` | Object storage browser (`minioadmin` / `minioadmin`) |

---

## Ingesting & Building the Knowledge Graph

Ingest plant documents (P&IDs, maintenance logs, inspection sheets, SOPs):

```bash
python -m tools.build_kg data/samples
```

Fast table-only ingestion (deterministic CSV extraction without LLM calls):

```bash
python -m tools.build_kg data/samples/work_orders.csv data/samples/inspection_records.csv
```

To sync new files on a schedule, place documents directly into `data/inbox/`.

---

## Evaluation & Benchmarks

Run the golden evaluation benchmark (28 multi-hop operational & root-cause questions):

```bash
python -m eval.run_eval
```

Run retrieval strategy ablations (**Vector** vs. **Local** vs. **PathRAG**):

```bash
python -m eval.run_ablation --modes vector,path
```

---

## Testing

Run the full offline test suite (405 passing tests with zero cloud dependencies):

```bash
pytest -q
```

---

## Repository Structure

```
plantmind/
├── libs/
│   └── core/                     # plantmind_core shared library
│       ├── bus/                  # RedisBus, streams, alert pub/sub
│       ├── cache/                # Semantic AnswerCache
│       ├── llm/                  # Vertex AI / Gemini multi-tier client
│       ├── notify/               # SlackNotifier & webhook dispatchers
│       ├── queues/               # Pipeline Route & Flow definitions
│       ├── schemas/              # Pydantic data contracts
│       └── storage/              # MinIO ObjectStore client
├── services/
│   ├── agents/                   # Multi-agent diagnostic runtime & watchers
│   ├── extraction/               # 6 extraction lanes (table, text, P&ID, OCR)
│   ├── gateway/                  # FastAPI edge proxy & Slack endpoints
│   ├── graphd/                   # Sole Neo4j writer & deduplication engine
│   ├── ingestion/                # Document classification & content-hash gate
│   ├── interview/                # Voice knowledge capture service
│   ├── mcp_server/               # Stdio Model Context Protocol tools
│   ├── resolution/               # Entity resolution & canonical IDs
│   ├── retrieval/                # PathRAG causal search & hybrid answerer
│   └── simulation/               # TEP physics simulator & PID controllers
├── ui/                           # React + Vite + Vanilla CSS frontend
│   ├── src/
│   │   ├── auth/                 # Persona routing & auth context
│   │   ├── components/           # AlertCard, DocumentViewer, P&ID canvas
│   │   ├── pages/app/            # Dashboard, Ask, Alerts, Compliance, Sim
│   │   └── pages/field/          # Field Co-Pilot & mobile checklist PWA
├── infra/                        # Dockerfiles, Celery configs, Neo4j schema
├── data/samples/                 # Plant sample corpus (P&IDs, SOPs, CSVs)
└── eval/                         # Golden QA benchmark & ablation harness
```

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Everything hangs on startup | Neo4j takes ~30s; services wait on its healthcheck. |
| `graph-init` "stopped" | Expected — it's a one-shot migration. Check it exited **0**. |
| Ingest reports every file as duplicate | Redis still holds the content-hash gate from a previous run. `FLUSHALL` and re-ingest. |
| Vector search errors on dimensions | `EMBEDDING_DIM` must match the model *and* the Neo4j vector index. |
| `SignatureDoesNotMatch` opening a document | `MINIO_PUBLIC_ENDPOINT` must be the host the **browser** uses. Presigned URLs are signed with it, never rewritten afterwards — SigV4 covers the Host header. |
| Everything 403s for an engineer | `SUPABASE_JWT_SECRET` is set but the `app_role` claim is missing — register the `custom_jwt_claims` hook, or unset the secret for an open local demo. |
| UI empty, API returns data | Check `VITE_GATEWAY_URL` and the browser console. |
| Document stuck, never in graph | Check `logs/extraction.log`; a failed lane releases its hash claim so a resubmit heals it. |
| Inspect a queue | `docker compose exec redis redis-cli LLEN q_extract_text` |
