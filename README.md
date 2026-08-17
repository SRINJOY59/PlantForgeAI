<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="ui/src/assets/logo-dark.png">
    <img src="ui/src/assets/logo-light.png" alt="PlantForge.ai" width="120">
  </picture>
</p>

<h1 align="center">PlantForge.ai</h1>
<p align="center"><em>Industrial Knowledge Intelligence — a unified asset &amp; operations brain</em></p>

<p align="center">
  <img alt="stack" src="https://img.shields.io/badge/stack-Docker%20Compose-2496ED">
  <img alt="tests" src="https://img.shields.io/badge/tests-405%20passing-16a34a">
  <img alt="golden set" src="https://img.shields.io/badge/golden%20set-28%20questions-7a54a0">
  <img alt="tep benchmark" src="https://img.shields.io/badge/simulation-Tennessee%20Eastman-blue">
</p>

---

Turns the documents scattered across a process plant — work orders, P&IDs,
SOPs, OEM manuals, emails, nameplate photos, trend charts — into one knowledge
graph, then answers operational questions with citations, warns before failures
repeat, and proves compliance.

Built for **ET AI Hackathon 2026, PS-8** (*Unified Asset & Operations Brain*).

---

## What it does

| Capability | How |
|---|---|
| **Ask anything, cited** | 3-mode retrieval: vector (single facts), local (asset-centric), **PathRAG** (causal/multi-entity). Every claim carries `[doc:id p3]`, and a citation opens the original document. |
| **Reasoning you can see** | PathRAG walks the plant's real topology and shows the chain it followed. |
| **Warns you first** | Agents watch every new failure, find sibling patterns, and investigate with LLM tool-calling before anyone asks. |
| **Turns warnings into work** | Each investigation drafts a corrective work order — facts harvested from the graph, prose from the model, approval from a human. |
| **Live TEP Plant Simulation** | Full physics simulation of the **Tennessee Eastman Process (TEP)** benchmark (Downs & Vogel, 1993) — 8 chemical species, 4 gas-phase reactions, 6 unit areas (Reactor, Condenser, Separator, Stripper, Compressor, Product Split), 12 regulatory PID loops, and 21 IDV fault injections. |
| **Interactive P&ID & Analytics** | Real-time interactive P&ID canvas overlaying live stream telemetry, multi-subplot time-series trends, phase-space trajectory portraits, and ISA 18.2 four-level envelope monitoring. |
| **Proves compliance** | Statutory obligations read from the graph, with evidence documents and one-click scheduling into the approval queue. |
| **Captures what is retiring** | A voice interview reads the graph first, asks about the assets that engineer actually worked on, and feeds the transcript back through ingestion. |
| **Trust by design** | Document facts / agent inferences / human corrections are separate tiers. Agent output is grounding-checked; ungrounded claims are flagged, never trusted. |
| **Answers before you ask** | The investigation that produces an alert pre-fills the answer cache — the follow-up question is an instant cache hit at zero extra cost. |
| **Works outside the app** | An MCP server exposes nine tools, so any AI assistant can query the plant graph with the same citations and grounding. |

---

## Architecture

```
                       ┌──────────── UI (React) ────────────┐
                       │  Ask · Graph · Alerts · Work Orders │
                       │  TEP Simulation · Compliance · PTW │
                       └───────────────┬────────────────────┘
                                       │  HTTP + WebSocket / SSE
                               ┌────────▼────────┐        ┌─────────────┐
                               │  gateway :8000  │◄───────┤ MCP server  │
                               │  modular routes │        │ (stdio)     │
                               └────────┬────────┘        └─────────────┘
               ┌───────────────────────┼──────────┐       └─────────────┘
               │                       │          │
       ┌───────▼──────┐        ┌───────▼───────┐  │  ┌──────────────┐
       │ retrieval    │        │ Redis         │  └─►│ MinIO        │
       │ :8001        │        │ telemetry bus │     │ raw documents│
       │ PathRAG      │        │ cache · locks │     └──────────────┘
       └───────┬──────┘        └───────┬───────┘
               │                       │  celery queues
               │        ┌──────────────┴───────────────────────┐
               │   ingestion → extraction (6 lanes) → resolution → graphd
               │        │                                          │
               └────────┴──────────► Neo4j (the graph) ◄───────────┘
                                           ▲
                                     agents runtime & watchers
                                     (tep-watcher · delta handler
                                      → investigate → alert
                                      → draft work order)
```

**Hard rules**

1. **Writes to Neo4j go through `graphd` only** — single writer, batched `UNWIND`, one graph version per batch.
2. Extractors emit `CandidateSubgraph` — never DB writes.
3. Every edge carries provenance `(doc_id, page/span, extractor_version, confidence, source)`.
4. All async messaging over Redis; the pipeline topology is declared once in `plantmind_core.queues.Flow`.
5. LLM access only via `plantmind_core.llm` — tiered cheap/mid/vision, retries, structured outputs.

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

Every other default works as-is. Docker Compose overrides the infra URLs to
service names automatically, so **the same `.env` serves both run modes**.

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

Brings up infra, applies the Neo4j schema (`graph-init` runs once and exits —
that's correct), seeds the TEP topology into Neo4j (`tep-seed`), starts the TEP physics simulator (`tep-sim`), TEP threshold watcher (`tep-watcher`), and all services. Gateway on `:8000`.

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
| TEP Simulator | http://localhost:8012 (proxied via `/sim/tep/*` on Gateway) |
| Neo4j browser | http://localhost:7474 (`neo4j` / your `NEO4J_PASSWORD`) |
| MinIO console | http://localhost:9001 |

---

## Building the knowledge graph

Ingest the sample corpus (42 documents across 3 plant units + TEP SOPs):

```bash
python -m tools.build_kg data/samples
```

Prints the pipeline topology, submits every file, watches the queues drain and
reports what landed. Re-runs are safe — the content-hash gate drops duplicates.

Cheap first spin (no LLM calls — tables parse deterministically):

```bash
python -m tools.build_kg data/samples/work_orders.csv data/samples/inspection_records.csv
```

Or drop a file into `data/inbox/` and the folder connector syncs it on schedule.

> **Re-ingesting after a wipe?** The content-hash gate lives in Redis. If Neo4j
> was cleared but Redis was not, every document is dropped as a duplicate and
> the graph stays empty. Clear the gate first:
> `docker compose exec -T redis redis-cli FLUSHALL`

---

## Evaluating

```bash
python -m eval.run_eval                  # 28 golden questions, as deployed
python -m eval.run_eval --limit 3        # quick spin
```

Reports answer accuracy (LLM judge), citation hit rate, mode-routing accuracy
and mean time-to-answer. Results land in `eval/results/`.

**Retrieval ablation** — the same questions forced through each strategy, so
retrieval is the only variable:

```bash
python -m eval.run_ablation              # vector vs local vs path
python -m eval.run_ablation --modes vector,path
python -m eval.run_ablation --limit 5
```

The answer cache is disabled per arm (a cache hit would make every arm look
identical) and questions that link no entity fall back to vector retrieval and
are counted, so no arm is credited for questions it did not handle. Accuracy is
also broken down by the question's intended mode — path retrieval should beat
the baseline on multi-hop causal questions and roughly tie on single-fact
lookups, which is what confirms the router is not paying traversal cost for
nothing.

---

## Testing

```bash
python -m pytest -q        # 405 tests, all offline (no API keys, no infra)
```

Every external dependency is faked — Redis via `fakeredis`, Neo4j/LLM/MinIO via
injected test doubles.

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
  simulation/       unified simulation engine (TEP physics model, controllers, runner)
  agents/           modularized runtime:
                    ├── handlers/ (delta, tep_alarm, process_limit)
                    ├── watchers/ (failure, tep, cstr, column)
                    ├── consumer.py (event loop runtime)
                    └── main.py (API endpoints)
  gateway/          the edge API:
                    ├── routes/
                    │   ├── simulation/ (envelopes, proxy, ws, idv)
                    │   └── (qa, moc, documents, graph, permit, reports, compliance)
                    └── main.py
  connectors/       scheduled data-source sync
  interview/        knowledge capture (voice + graph-aware questioning)
  mcp_server/       MCP tools over stdio

infra/              containers.py, celery_workers.py, autoscaler, docker/, neo4j/
tools/              serve.py, build_kg.py, autoscale.py
config/             tep_envelopes.json (ISA 18.2 operating envelopes)
eval/               golden QA set, runner, retrieval ablation
docs/               architecture reports, demo script
data/samples/       the demo corpus (TEP SOPs, P&IDs, inspection records)
ui/                 React + Vite + Vanilla CSS + D3 P&ID canvas
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
