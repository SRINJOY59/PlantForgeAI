# PlantMind — Industrial Knowledge Intelligence

Turns the documents scattered across a process plant — work orders, P&IDs,
SOPs, OEM manuals, emails, nameplate photos, trend charts — into one
knowledge graph, then answers operational questions with citations, warns
before failures repeat, and proves compliance.

Built for ET AI Hackathon 2026, PS-8 (*Unified Asset & Operations Brain*).

---

## What it does

| Capability | How |
|---|---|
| **Ask anything, cited** | 3-mode retrieval: vector (single facts), local (asset-centric), **PathRAG** (causal/multi-entity). Every claim carries `[doc:id p3]`. |
| **Reasoning you can see** | PathRAG walks the plant's real topology and shows the chain it followed. |
| **Warns you first** | Agents watch every new failure, find sibling patterns, and investigate with LLM tool-calling before anyone asks. |
| **Trust by design** | Document facts / agent inferences / human corrections are separate tiers. Agent output is grounding-checked; ungrounded claims are flagged, never trusted. |
| **Answers before you ask** | The agent investigation that produces an alert pre-fills the answer cache — the technician's question is an instant cache hit, at zero extra cost. |
| **Stays current** | Connectors sync folders/buckets into the pipeline on a schedule. |

---

## Architecture

```
                       ┌──────────── UI (React) ────────────┐
                       │  Ask · Graph · Alerts · Documents   │
                       └───────────────┬────────────────────┘
                                       │  HTTP + SSE
                              ┌────────▼────────┐
                              │  gateway :8000  │  edge: CORS, uploads,
                              └────────┬────────┘  citations, alert fan-out
              ┌───────────────────────┼────────────────────┐
              │                       │                    │
      ┌───────▼──────┐        ┌───────▼───────┐    ┌───────▼──────┐
      │ retrieval    │        │ Redis (bus)   │    │ MinIO        │
      │ :8001        │        │ queues·locks  │    │ raw docs     │
      │ PathRAG      │        │ streams·cache │    └──────────────┘
      └───────┬──────┘        └───────┬───────┘
              │                       │  celery queues
              │        ┌──────────────┴───────────────────────┐
              │   ingestion → extraction (6 lanes) → resolution → graphd
              │        │                                          │
              └────────┴──────────► Neo4j (the graph) ◄───────────┘
                                          ▲
                                     agents (delta stream →
                                     detect → investigate → alert)
```

**Hard rules**
1. **Writes to Neo4j go through `graphd` only** (single writer, batched `UNWIND`).
2. Extractors emit `CandidateSubgraph` — never DB writes.
3. Every edge carries provenance `(doc_id, page/span, extractor_version, confidence, source)`.
4. All async messaging over Redis; the pipeline topology is declared in `plantmind_core.queues.Flow`.
5. LLM access only via `plantmind_core.llm` (tiered cheap/mid/vision, retries, structured outputs).

---

## Prerequisites

- **Docker Desktop** (running)
- **Python 3.11+**
- **Node 18+**
- An **OpenRouter API key** (open-weight models: Qwen / DeepSeek)

---

## Setup

### 1. Configure

```bash
cd plantmind
cp .env.example .env
```

Edit `.env` — the only value you *must* set:

```ini
OPENROUTER_API_KEY=sk-or-...
```

The infra defaults (`localhost` URLs, `NEO4J_PASSWORD=plantmind_dev`) work
as-is. Docker Compose overrides the URLs to service names automatically, so
**the same `.env` serves both run modes**.

### 2. Python environment

```bash
python -m venv .venv
.venv\Scripts\pip install -e libs\core[celery,dev]
.venv\Scripts\pip install minio openpyxl fakeredis pypdfium2 pillow ^
                          fastapi "uvicorn[standard]" python-multipart neo4j

# put services/ on sys.path so `python -m graphd.tasks` works from anywhere
echo <abs-path-to-repo>\services > .venv\Lib\site-packages\plantmind_services.pth
```

### 3. Frontend

```bash
cd ui
npm install
cp .env.example .env      # VITE_GATEWAY_URL=http://localhost:8000
```

---

## Running

### Option A — everything in Docker (demo / judges)

```bash
docker compose up --build
```

Brings up infra, applies the Neo4j schema (`graph-init` runs once and exits
— that's correct), and starts all 9 services. Gateway on `:8000`.

### Option B — local dev (recommended while building)

Infra in Docker, services in your venv — no rebuild on code changes:

```bash
python -m tools.serve
```

One command: infra → schema → 6 celery workers → agents → retrieval:8001 →
gateway:8000. `Ctrl+C` stops everything. Logs in `logs/`.

### Then the UI

```bash
cd ui && npm run dev        # http://localhost:5173
```

| Service | URL |
|---|---|
| UI | http://localhost:5173 |
| Gateway (API) | http://localhost:8000 |
| Retrieval | http://localhost:8001 |
| Neo4j browser | http://localhost:7474 (`neo4j` / `plantmind_dev`) |
| MinIO console | http://localhost:9001 |

---

## Building the knowledge graph

Ingest the sample corpus (33 documents across 3 plant units):

```bash
python -m tools.build_kg data/samples
```

Prints the pipeline topology, submits every file, watches the queues drain,
and reports what landed. Re-runs are safe — the content-hash gate drops
duplicates.

Cheap first spin (no LLM calls — tables parse deterministically):

```bash
python -m tools.build_kg data/samples/work_orders.csv data/samples/inspection_records.csv
```

Or drop a file into `data/inbox/` — the folder connector syncs it on its
schedule.

---

## Evaluating

```bash
python -m eval.run_eval              # all 28 golden questions
python -m eval.run_eval --limit 3    # quick spin
```

Reports answer accuracy (LLM judge), citation hit rate, mode-routing
accuracy and mean time-to-answer. Results land in `eval/results/`.

---

## Testing

```bash
python -m pytest -q        # ~190 tests, all offline (no API keys, no infra)
```

Every external dependency is faked — Redis via `fakeredis`, Neo4j/LLM/MinIO
via injected test doubles.

---

## Repo layout

```
libs/core/          shared package (plantmind_core)
  ├── schemas/      pydantic contracts — the only shapes crossing services
  ├── queues/       Route + Flow: the pipeline topology, declared once
  ├── bus/          RedisBus: queues, locks, streams, cursors
  ├── cache/        AnswerCache: semantic answer cache
  ├── llm/          tiered client, structured outputs, ToolAgent
  └── storage/      ObjectStore (MinIO)

services/<name>/    service.py (pure logic) + tasks.py (celery adapter)
  ingestion/        hash gate → classify → route
  extraction/       6 lanes: table, text, pnid, manual, mail, imaging
  resolution/       canonical ids
  graphd/           SOLE Neo4j writer + denoise
  retrieval/        linker → router → pathfinder → pruner → assembler
  agents/           watchers (detect) → investigator (LLM tools) → alerts
  gateway/          the edge API
  connectors/       scheduled data-source sync

infra/              containers.py, celery_workers.py, docker/, neo4j/
tools/              serve.py, build_kg.py, local_pipeline.py
eval/               golden QA set + runner
data/samples/       the demo corpus
ui/                 React + Vite + Tailwind + Supabase
```

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Everything hangs on startup | Neo4j takes ~30s; services wait on its healthcheck. |
| `graph-init` "stopped" | Expected — it's a one-shot migration. Check it exited **0**. |
| Vector search errors on dimensions | `EMBEDDING_DIM` must match the model *and* the Neo4j vector index. |
| UI empty, API returns data | Check `VITE_GATEWAY_URL` and the browser console. |
| Document stuck, never in graph | Check `logs/extraction.log`; a failed lane releases its hash claim so a resubmit heals it. |
| Inspect a queue | `docker exec plantmind-redis-1 redis-cli LLEN q_extract_text` |
