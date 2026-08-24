<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="ui/src/assets/logo-dark.png">
    <img src="ui/src/assets/logo-light.png" alt="PlantForge.ai" width="140">
  </picture>
</p>

<h1 align="center">PlantForge.ai</h1>
<p align="center"><em>Industrial Knowledge Intelligence &amp; Operational AI Co-Pilot for Process Plants</em></p>

<p align="center">
  <img alt="deployment" src="https://img.shields.io/badge/deployed-GKE%20Autopilot-4285F4">
  <img alt="llm" src="https://img.shields.io/badge/LLM-Vertex%20AI%20(Workload%20Identity)-4285F4">
  <img alt="graph" src="https://img.shields.io/badge/graph-Neo4j%205%20%2B%20native%20vector-008CC1">
  <img alt="historian" src="https://img.shields.io/badge/historian-TimescaleDB-FDB515">
  <img alt="simulation" src="https://img.shields.io/badge/physics-Tennessee%20Eastman%2020--state-blue">
  <img alt="tests" src="https://img.shields.io/badge/tests-529%20passing-16a34a">
  <img alt="services" src="https://img.shields.io/badge/services-14%20images%20%C2%B7%2022%20workloads-6b7280">
</p>

<p align="center">
  <strong>Live:</strong>
  <a href="https://ui.8.233.53.227.nip.io">ui.8.233.53.227.nip.io</a> ·
  <a href="https://api.8.233.53.227.nip.io/health">api health</a>
</p>

---

## The problem

A process plant's most valuable knowledge is unwritten. It lives in P&IDs nobody
has opened in years, work orders nobody aggregates, incident reports filed and
forgotten, and in the heads of engineers about to retire. When a pump trips at
3 a.m., the answer usually exists — in a document, a maintenance record, and a
standard — but no one can connect the three in time.

**PlantForge turns that corpus into a queryable knowledge graph, grounds every
answer in the documents it came from, and refuses to guess.**

Built for **ET AI Hackathon 2026, PS-8** — *Unified Asset & Operations Brain*.

---

## What makes it different

Most RAG systems retrieve chunks that *look like* the question. Plant questions
are not like that. *"Why did P-101A trip last month?"* needs a **causal chain**
across equipment topology, failure history and governing standards — evidence
that is structurally connected, not textually similar.

| | conventional RAG | PlantForge |
|---|---|---|
| retrieval unit | text chunk | **flow-scored path through the graph** |
| "why" questions | similar-sounding passages | causal chain: equipment → failure → procedure |
| provenance | cite whatever was retrieved | **citations verified against the context** |
| a fabricated citation | invisible | flagged `unverified` in red |
| answering with no evidence | silently confident | badged `general knowledge` |

Three things follow from that, and they are the core of the submission:

**1. Retrieval is a graph traversal, not a similarity search.** Paths are scored
by a flow model — resource decays with length, splits across branching, and is
weighted by extraction confidence, so a chain through a plant-wide hub is
suppressed in favour of specific structure. → [Appendix A1](docs/appendix/A1-pathrag-math.md)

**2. The graph prunes itself.** A denoise pass drops document-ids miscaught as
equipment, merges synonymous failure modes, and recovers `mechanism CAUSES mode`
edges — with the LLM allowed to *propose* but never to *invent*.

**3. Confidence is earned, not asserted.** Grounding is read off what the answer
**cited**, checked against what was actually put in front of the model.
Deterministic, no second LLM call.

---

## Measured results

Not projections. `eval/results/eval_20260715_183028.json`, 28 hand-written
multi-hop cases, cache disabled:

```
   ╔══════════════════════════════════════════════════════════════╗
   ║  Answer accuracy (strict)         0.64    18/28 correct      ║
   ║  Citation hit rate                0.82    mechanical         ║
   ║  Mode routing accuracy            0.93    mechanical         ║
   ║  Mean time to answer             11.2 s   end to end         ║
   ╚══════════════════════════════════════════════════════════════╝
```

Only *accuracy* uses an LLM judge. Citation hit rate and routing accuracy are
scored **mechanically** against the golden file, so a drifting judge cannot move
them.

**Citation hit rate (0.82) exceeding accuracy (0.64) is the interesting number:**
the system finds the right documents more often than it reasons correctly over
them. The remaining loss is in synthesis, not retrieval.

Live graph from the 44-document sample corpus: **764 nodes, 1054 edges, 98
embedded chunks**. → [Appendix A3](docs/appendix/A3-evaluation-metrics.md)

---

## Capabilities

| Capability | Mechanism |
|---|---|
| **PathRAG causal retrieval** | 3-mode router (vector / local / path) with flow-pruned graph traversal and `[doc:id p3]` provenance |
| **Self-pruning knowledge graph** | Deterministic node pruning → LLM synonym reconciliation → causal structure recovery, all reversible |
| **Grounding verification** | Citations checked against supplied context; fabricated provenance flagged red |
| **TEP physics simulation** | 20-state reduced-order Tennessee Eastman: 8 species, 4 reactions, 12 PID loops, 21 IDV faults, 1 Hz |
| **TimescaleDB historian** | Redis stream → bulk `COPY` → hypertable, columnar compression, 90-day retention |
| **Autonomous RCA agents** | Process-limit breach → multi-tool investigation → grounded alert → drafted work order |
| **Statutory compliance** | OISD-STD-119 / IBR / API 510-570-653 tracked from the graph with PM02 drafting |
| **Voice knowledge capture** | WebRTC interview (Pipecat + Deepgram) that harvests undocumented expertise before retirement |
| **Multi-persona reasoning** | Prompt grounding tuned per role: operator, engineer, maintenance, safety |
| **Field Co-Pilot PWA** | Mobile-first, multilingual TTS (`hi`, `bn`, `ta`, `te`, `mr`, `gu`), tag scanning |
| **MCP server** | 9 stdio tools exposing plant topology and telemetry to external assistants |

---

## Architecture

```
                    ┌───────────── UI (React · Vite · PWA) ─────────────┐
                    │  Ask · Graph · Alerts · Compliance · Simulation   │
                    │  MoC · Interview · Field Co-Pilot · Permits       │
                    └───────────────────────┬──────────────────────────-┘
                                            │ HTTPS · SSE · WebSocket · WebRTC
                              ┌─────────────▼─────────────┐
                              │   GCE L7 LB + managed TLS │
                              │  ui.<host>   api.<host>   │
                              └─────────────┬─────────────┘
                                            │
                          ┌─────────────────▼──────────────────┐
                          │  gateway :8000  — the ONLY place   │
                          │  auth is decided (Supabase JWT)    │
                          └─────────────────┬──────────────────┘
                                            │
        ┌───────────────┬───────────────────┼──────────────────┬──────────────┐
        ▼               ▼                   ▼                  ▼              ▼
  ┌──────────┐   ┌────────────┐     ┌─────────────┐    ┌────────────┐  ┌───────────┐
  │retrieval │   │ agents-api │     │  interview  │    │  tep-sim   │  │ MCP stdio │
  │  :8001   │   │   :8002    │     │   WebRTC    │    │  20-state  │  │  9 tools  │
  │ PathRAG  │   │ MoC · RCA  │     │  Pipecat    │    │  ODE 1 Hz  │  └───────────┘
  │ +GraphQL │   └────────────┘     └─────────────┘    └─────┬──────┘
  └────┬─────┘                                               │ telemetry
       │                                                     ▼
       │        ┌──────────────── Redis ────────────────┐  ┌──────────────┐
       │        │ celery broker · streams · answer cache│  │ TimescaleDB  │
       │        │ locks · cursors · hash gate · rate lim│  │  hypertable  │
       │        └───────────────┬───────────────────────┘  └──────────────┘
       │                        │ 7 queues
       │   ┌────────────────────▼──────────────────────────────┐
       │   │ ingestion → extraction ×6 lanes → resolution      │
       │   │      ↓ content-hash gate    ↓ canonical ids       │
       │   │                    write buffer → graphd (×1)     │
       │   └────────────────────┬──────────────────────────────┘
       │                        │ single writer, MERGE
       └────────────────────────▼──────────────────────────────
                          Neo4j 5  ·  graph + native vector index
                                    ▲
                        agents runtime · watchers · denoise pass
```

### Guardrails that are correctness requirements, not tuning

| constraint | why it cannot be relaxed |
|---|---|
| `graphd` replicas **= 1** | single graph writer; concurrent `MERGE` on one entity corrupts the graph |
| `connectors` replicas **= 1** | embedded beat scheduler — two replicas double every scan |
| canonical ids are a **pure function** | `P 101 A` / `p-101a` / `P101A` → `equip:P-101A` with no coordination between workers |
| `acks_late` + idempotent handlers | at-least-once delivery is only safe because every handler is replay-safe |
| scale extraction **out**, never **up** | replicas bring their own memory; extra prefork children do not |

→ [Appendix A4](docs/appendix/A4-systems-architecture.md)

---

## The retrieval engine

```
  q ──▶ condense ──▶ embed ──▶ semantic cache ──hit──▶ answer
                       │
                  QueryLinker            tags · standard codes · title phrases
                       │
                  ModeRouter             rules only — no LLM, cannot drift
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
    VECTOR          LOCAL           PATH
    ANN over      1-hop rels     enumerate trails (undirected, ≤4 hops)
    chunks        + hybrid       type-constrained per question
                  + history              ↓
                                  FLOW PRUNE
                                         ↓
                                  dedupe overlapping, keep 15
        └──────────────┴──────────────┘
                       │
              + plant digest (live aggregate Cypher)
              + engineer corrections  ← placed FIRST, they overrule sources
                       │
                    Answerer ──▶ Grounding ──▶ (documents | general | unverified)
```

**The flow score.** Each seed injects one unit of resource; what survives to the
far end is the path's score:

```
                       α · max(κ(e), κ_min)
   flow(p) =    ∏    ─────────────────────────
              e ∈ p    max(deg(src(e)) − 1, 1)

   α = 0.8 decay   κ = extraction confidence   deg = branching in T(q)
```

Two properties fall straight out: **monotone decay with length** (no separate
length prior needed) and **hub penalisation** (a node of degree 40 divides by
39, so paths through plant-wide hubs lose to specific structure).

**The key modification is the type constraint.** `MENTIONED_IN` is near-complete
bipartite — admit it unconditionally and every entity pair connects within two
hops, making path existence meaningless. It is readmitted only for compliance
questions, where document co-occurrence *is* the evidence.

→ [Appendix A1](docs/appendix/A1-pathrag-math.md) for the full formalism.

---

## Physics simulation

Three live digital twins on `scipy.solve_ivp`, 1 Hz wall clock.

**Tennessee Eastman** — 20 states, reduced from the 50+ of Downs & Vogel (1993):

```
   r₁: A+C+D → G      r₂: A+C+E → H      r₃: A+E → F      r₄: 3D → 2F

   dx      x_feed − x     Sᵀr                dT_r     Q_rx − Q_cool
   ── =   ──────────── + ─────────           ──── =  ───────────────
   dt         τ_r        V/1000               dt      V · ρCp / 1000
```

**CSTR** — the canonical runaway system: generation rises superlinearly through
Arrhenius while removal is only linear.

**Distillation** — 12 stages, constant relative volatility, feeding a live
McCabe–Thiele panel.

**PID with bumpless reset.** At steady state `u = K_i·I`, so a naive zero-reset
slams every valve shut. Seeding `I = u_hold / K_i` preserves the holding output —
without it, resetting the TEP sim collapsed every controlled flow at once and
tripped a burst of low-flow alarms across three units.

→ [Appendix A2](docs/appendix/A2-simulation-odes.md)

---

## Security

Auth is decided at **exactly one edge**. Everything behind the gateway is a
private network with no internet route.

| threat | control |
|---|---|
| forged / replayed token | Supabase HS256, **audience and expiry both enforced** |
| algorithm confusion | `algorithms=["HS256"]` pinned — no `alg: none` |
| privilege escalation | 5-tier hierarchy; unknown role falls back to `operator`, never higher |
| endpoint added unprotected | auth applied **per-router**, so new endpoints are protected by default |
| cross-tenant read | Postgres RLS; the admin policy reads the **JWT claim**, avoiding infinite recursion |
| pickle RCE | Celery `json`-only serializer |
| stored XSS on uploads | `nosniff` + `CSP default-src 'none'` + `blob:` rendering |
| abuse / cost exhaustion | Redis fixed-window limiter keyed on `sub`, not IP |
| SA key leakage | **Workload Identity** — no key file exists anywhere |
| fabricated citation | deterministic grounding check |

→ [Appendix A5](docs/appendix/A5-security.md), including the gaps we chose to
leave open and why.

---

## Cost

GKE Autopilot bills **resource requests**, not nodes or usage — so right-sizing
requests *is* the cost lever. Measured from the live cluster:

```
   7.15 vCPU  ·  21.63 GiB  ·  50 GiB PVC  ·  1 L7 LB      ≈ $425/month
   LLM inference (Gemini via Vertex)                        ~$0.003/question
   Embeddings (FastEmbed, in-process)                       $0 — paid for in RAM
```

Deleting the cluster between demos takes that to ~$0 and is by far the largest
lever. → [Appendix A6](docs/appendix/A6-cost-model.md)

---

## Engineering notes

Problems worth reading about, because the fix is not the obvious one.

<details>
<summary><strong>A simulation that went dark without crashing</strong></summary>

The TEP sim stopped serving while the pod stayed `Running` with **0 restarts**
and CPU pegged at its exact 1000m limit.

```python
sleep = max(0.0, self.dt - elapsed)
if sleep > 0:                    # ← the bug
    await asyncio.sleep(sleep)
```

A tick that overran `dt` left `sleep == 0`, so the `await` was skipped and the
loop spun with **no yield at all**. uvicorn never got scheduled, so it stopped
accepting connections — alive, healthy to Kubernetes, serving nothing.

Diagnosis was slow because uvicorn's access log has no timestamps: old `200 OK`
lines looked live. Counting them twice 15 s apart gave a delta of **zero**.

Fixed by always awaiting (`sleep(0)` still yields) plus an overrun watchdog that
resets to nominal after 3 consecutive over-budget ticks.
</details>

<details>
<summary><strong>28 documents stranded by an OOM</strong></summary>

`extraction-text` ran `-c 32` against a 2 GiB limit. Celery prefork forks one
child per slot and **each child lazily builds its own FastEmbed model** (~0.5 GiB),
so the first real ingestion burst put 32 models in one container and the kernel
OOM-killed it (exit 137).

With `acks_late`, 28 in-flight tasks went to kombu's `unacked` hash and would
not have been redelivered until the visibility timeout expired an hour later.
Recovered them by replaying `unacked` back onto the queue.

Lesson encoded in the manifests: **scale extraction out with the HPA, never up
with `-c`.** Replicas bring their own memory; forks do not.
</details>

<details>
<summary><strong>WebRTC that negotiated and then died</strong></summary>

Every `POST /api/offer` returned 500 with `CancelledError` out of
`setRemoteDescription`.

Browsers anonymise host ICE candidates as `<uuid>.local` (mDNS) for privacy.
aioice spins up a shared multicast listener to resolve them — and **GCP's VPC
carries no multicast at all**, so the listener never properly came up. The
failed lookup was harmless and handled; *closing* the listener during routine
transport teardown was what threw.

Fixed by stubbing the resolver: `.local` candidates are unresolvable from a pod
by construction, so they are skipped and the connection completes on the
server-reflexive pair — which is what would have happened anyway.
</details>

<details>
<summary><strong>A tag regex that invented equipment</strong></summary>

```python
r"\b([A-Za-z]{1,4})[-\s]?(\d{2,5})\s*([A-Za-z]?)\b"

'unit 200 P-101A tripped'     → ['UNIT-200P']    ← P-101A lost
'see WO 4471 K-301 vibration' → ['WO-4471K']     ← K-301 lost
```

The space tolerance that lets `P 101 A` parse as one tag also let the optional
trailing letter reach across a word boundary and eat the **next** tag's first
character — inventing phantom equipment and dropping real tags, on both the
ingestion and the live query path.

Fixed with a lookahead that declines the suffix when the letter has its own
digits after it — i.e. when it is *starting* a tag rather than ending one.
</details>

<details>
<summary><strong>"Diagnose with AI" on a diagnosis that had expired</strong></summary>

The RCA request reached the agent fine; the lookup failed. Two stores with
disagreeing lifetimes: `diagnoses:live` is capped by **entry count** (5000),
while `diagnoses:index:<id>` is capped by **time** (24 h). So the UI kept
rendering a diagnosis, with a live button, long after its lookup key had gone.

Fixed by falling back to the stream on an index miss and re-indexing the hit —
tying the two together by construction. Tuning the TTL would have drifted again;
an entry-capped stream and a time-capped key diverge by definition.
</details>

<details>
<summary><strong>Deployment scars</strong></summary>

- **Neo4j** parses *every* `NEO4J_*` env var as a config setting, so a
  `NEO4J_PASSWORD` added only to build `NEO4J_AUTH` was read as a bogus setting
  and refused to boot. Renamed to `NEO_PW`.
- **`.env` inline comments** survive `kubectl create secret --from-env-file`, so
  pydantic received `"1536   # note"` and every Python service crash-looped on
  `int_parsing`.
- **`.env` localhost URLs** layered *over* the ConfigMap (Secret wins in
  `envFrom`), overriding in-cluster service names. Now excluded at deploy time.
- **Autopilot node pools "cannot be accessed or modified"**, so the documented
  plan of adding a Standard pool for coturn does not exist on this cluster.

→ [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
</details>

---

## Quick start

### Prerequisites
Docker Desktop · Python 3.11+ · Node 18+ · Vertex AI credentials or an
OpenRouter key

### Run it

```bash
cp .env.example .env          # add GCP project / API keys
gcloud auth application-default login
docker compose up --build
```

| Service | URL |
|---|---|
| Web UI | `http://localhost:5173` |
| Gateway API | `http://localhost:8000` |
| Retrieval (REST + GraphQL) | `http://localhost:8001` |
| TEP simulator | `http://localhost:8012` |
| Neo4j Browser | `http://localhost:7474` |
| MinIO Console | `http://localhost:9001` |

### Local development
Infra in Docker, Python services hot-reloading locally:

```bash
python -m tools.serve
cd ui && npm run dev
```

### Build the knowledge graph

```bash
python -m tools.build_kg data/samples          # full pipeline
```

Or drop documents into `data/inbox/` — the folder connector syncs on a 5-minute
beat.

### Evaluate

```bash
python -m eval.run_eval                        # 28-case golden set
python -m eval.run_ablation --modes vector,path
```

### Test

```bash
pytest -q                                      # 529 passing, no cloud calls
```

---

## Production deployment

Staged and idempotent — each stage is safe to re-run:

```bash
./scripts/deploy_gke.sh cluster    # Autopilot cluster + Artifact Registry
./scripts/deploy_gke.sh wi         # Workload Identity → Vertex AI, no key file
./scripts/deploy_gke.sh images     # build + push 14 images
./scripts/deploy_gke.sh config     # static IP, nip.io hosts, pin image tags
./scripts/deploy_gke.sh secrets    # namespace, Secret, file ConfigMaps
./scripts/deploy_gke.sh apply      # kubectl apply -k k8s/
```

`nip.io` is itself a decision: `ui.<IP>.nip.io` resolves without registering a
domain and still receives a real Google-managed certificate.

---

## Repository layout

```
plantmind/
├── libs/core/plantmind_core/    # shared: bus · cache · llm · queues · schemas · tags
├── services/
│   ├── retrieval/               # PathRAG: linker · router · pathfinder · pruner · grounding
│   ├── graphd/                  # sole Neo4j writer + denoise (KG pruning)
│   ├── extraction/              # 6 lanes: table · text · manual · email · pnid · image
│   ├── ingestion/               # classification + content-hash gate
│   ├── resolution/              # canonical ids
│   ├── agents/                  # RCA runtime, watchers, standards watch
│   ├── simulation/              # TEP · CSTR · column + PID bank
│   ├── interview/               # WebRTC voice knowledge capture
│   ├── historian/               # Redis → TimescaleDB sink
│   ├── gateway/                 # FastAPI edge: auth · rate limit · security headers
│   └── mcp_server/              # 9 stdio MCP tools
├── ui/src/                      # React · Vite · PWA
├── k8s/                         # manifests, HPAs, ingress, managed cert
├── eval/                        # golden set + ablation harness
└── docs/appendix/               # A1 PathRAG math · A2 ODEs · A3 metrics
                                 # A4 systems · A5 security · A6 cost
```

---

## Technical appendix

Written for reviewers who want the derivations rather than the claims.

| | |
|---|---|
| [A1 — PathRAG](docs/appendix/A1-pathrag-math.md) | flow equation, type constraint, trail semantics, grounding classifier |
| [A2 — Simulation](docs/appendix/A2-simulation-odes.md) | TEP / CSTR / column ODEs, PID with anti-windup |
| [A3 — Evaluation](docs/appendix/A3-evaluation-metrics.md) | metric definitions, judge protocol, ablation design |
| [A4 — Systems](docs/appendix/A4-systems-architecture.md) | Redis · Celery · Kubernetes · GraphQL · REST |
| [A5 — Security](docs/appendix/A5-security.md) | 10 threats with controls, plus known gaps |
| [A6 — Cost](docs/appendix/A6-cost-model.md) | measured footprint and the cost model |

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Everything hangs on startup | Neo4j takes ~30 s; services wait on its healthcheck |
| `graph-init` "stopped" | Expected — one-shot migration. Check it exited **0** |
| Every file reports as duplicate | Redis still holds the content-hash gate. `FLUSHALL` and re-ingest |
| Vector search dimension error | `EMBEDDING_DIM` must match the model *and* the Neo4j index |
| `SignatureDoesNotMatch` on a document | `MINIO_PUBLIC_ENDPOINT` must be the host the **browser** uses — SigV4 covers the Host header |
| Everything 403s for an engineer | `SUPABASE_JWT_SECRET` set but `app_role` claim missing — register the `custom_jwt_claims` hook |
| UI empty, API returns data | Check `VITE_GATEWAY_URL` and the browser console |
| Document stuck, never in graph | Check `logs/extraction.log`; a failed lane releases its hash claim so a resubmit heals it |
| Sim shows "offline", pod is Running | Check CPU — if pegged at its limit the tick loop is starving the event loop |
| Inspect a queue | `docker compose exec redis redis-cli LLEN q_extract_text` |
