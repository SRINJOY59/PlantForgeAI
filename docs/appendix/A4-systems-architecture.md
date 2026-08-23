# Appendix A4 — Systems Architecture

Redis · Celery · Kubernetes · GraphQL · REST · Neo4j · MinIO.
Source of truth: `libs/core/plantmind_core/`, `services/`, `k8s/`.

---

## A4.1 Service topology

14 container images, 21 workloads. Everything behind one gateway.

```
                        Internet
                            │
                            ▼
      ┌───────────────────────────────────────────────┐
      │  GCE L7 Load Balancer + Google-managed TLS    │
      └────────┬──────────────────────────┬───────────┘
               │ ui.<host>                │ api.<host>
               ▼                          ▼
         ┌──────────┐          ┌────────────────────────┐
         │ ui  ×2   │          │  /interview → interview│
         │ nginx    │          │  /          → gateway  │
         │ SPA      │          └──────┬─────────────────┘
         └──────────┘                 │  JWT verified here
                                      │  and only here
        ┌─────────────────────────────┼──────────────────────────┐
        ▼                             ▼                          ▼
  ┌───────────┐              ┌──────────────┐          ┌────────────────┐
  │ retrieval │              │  agents-api  │          │   tep-sim      │
  │    ×2     │              │      ×2      │          │  digital twin  │
  │ REST +    │              │  MoC / RCA   │          │                │
  │ GraphQL   │              └──────────────┘          └────────────────┘
  └─────┬─────┘
        │
        ▼
  ┌───────────────────────────────────────────────────────────────┐
  │                     STATE  (StatefulSets)                     │
  │   neo4j-0        redis-0            minio-0                   │
  │   graph + vector broker/streams/    raw document blobs        │
  │   index          cache/locks        (presigned URLs)          │
  │   20 GiB PVC     10 GiB PVC         20 GiB PVC                │
  └───────────────────────────────────────────────────────────────┘
        ▲
        │  single writer
  ┌─────┴──────────────────────────────────────────────────────────┐
  │                   CELERY WORKER POOL                           │
  │  ingestion · extraction-{text,wo,pnid} · resolution · graphd   │
  │  connectors · agents · diagnostics · historian · tep-watcher   │
  └────────────────────────────────────────────────────────────────┘
```

---

## A4.2 Redis — five distinct roles

Redis is not "a cache" here. It carries five separate responsibilities, each
with its own key namespace (`plantmind_core/keys.py` — renaming any of these is
a breaking change across every service):

```
  ┌──────────────────┬──────────────────────────────────────────────────┐
  │ 1. BROKER        │ Celery task queues                               │
  │                  │   q_classify q_parse_wo q_extract_pnid           │
  │                  │   q_extract_text q_resolve q_write q_connectors  │
  ├──────────────────┼──────────────────────────────────────────────────┤
  │ 2. STREAMS       │ XADD/XREAD event log — durable, replayable       │
  │                  │   graph:deltas          every committed batch    │
  │                  │   alerts:critical       agents → UI (SSE)        │
  │                  │   diagnoses:live        diagnostics → UI         │
  │                  │   rca:requests          UI → agents              │
  │                  │   work_orders:drafts    agent-proposed WOs       │
  ├──────────────────┼──────────────────────────────────────────────────┤
  │ 3. IDEMPOTENCY   │ doc:<sha256>            content-hash claim gate  │
  │                  │ lock:extract:<lane>:<h> single-flight extraction │
  │                  │ cache:extract:<lane>:<h>extraction result cache  │
  │                  │ agents:alerted          alert fingerprints       │
  ├──────────────────┼──────────────────────────────────────────────────┤
  │ 4. WRITE BUFFER  │ graphd:write_buffer     resolver RPUSHes here    │
  │                  │ graphd:write_dlq        unparseable items        │
  │                  │ graphd:flush_lock       single-writer mutex      │
  │                  │ graph:version           INCR per committed batch │
  ├──────────────────┼──────────────────────────────────────────────────┤
  │ 5. CACHE/CURSOR  │ answercache:entries     semantic answer cache    │
  │                  │ answercache:lru         eviction ordering        │
  │                  │ cursor:<name>           connector sync positions │
  │                  │ ratelimit:<bucket>:<who>fixed-window limiter     │
  └──────────────────┴──────────────────────────────────────────────────┘
```

**Why the content-hash gate matters.** `SET doc:<sha256> 1 NX` is atomic, so
two concurrent ingests of the same bytes cannot both pass. The loser deletes
its staged copy and returns `duplicate`. Crucially, a lane that fails *after*
the gate calls `release_document()` — otherwise a transient failure would brick
that file permanently and no resubmission could heal it.

---

## A4.3 Celery — delivery policy in one place

Every worker is built by `WorkerApp` (`plantmind_core/celeryapp/worker_app.py`),
so delivery semantics are declared once and cannot drift per service:

```python
task_serializer      = "json"    # pickle over the wire is an RCE waiting to happen
accept_content       = ["json"]
task_ignore_result   = True      # outcomes flow via streams and the graph itself
task_acks_late       = True      # ack AFTER the task runs
task_reject_on_worker_lost = True
worker_prefetch_multiplier = 1   # a 30 s VLM call must not hoard quick parses
task_soft_time_limit = 540       # warn at 9 min
task_time_limit      = 600       # hard kill at 10, then requeue
```

`acks_late` gives **at-least-once** delivery, which is only safe because every
handler is idempotent by construction — content hashes at ingest, `MERGE` at
write, `prov_hash` keys on edges.

**Pipeline topology** is declared in `Flow` and nowhere else; services contain
no routing logic, they ask `Flow` what comes next:

```
   upload / connector / API
            │
            ▼
   ┌─────────────────┐
   │   q_classify    │  ingestion ×1, c=4
   │  sha256 → dedup │  LLM classifies: table|pnid|text|manual|email|image
   └────────┬────────┘
            │  Flow.extraction_for[kind]
   ┌────────┼──────────────────┬──────────────────┐
   ▼        ▼                  ▼                  ▼
 q_parse_wo  q_extract_pnid   q_extract_text    (correction)
 tables      drawings+images  text/manual/email  human override
 c=4         c=4              c=4  HPA 1→8       ↓
   │           │                │                │
   └───────────┴────────┬───────┴────────────────┘
                        ▼
                 ┌─────────────┐
                 │  q_resolve  │  entity resolution, canonicalisation
                 └──────┬──────┘
                        ▼
              graphd:write_buffer  (Redis list)
                        │
                        ▼
                 ┌─────────────┐
                 │   q_write   │  graphd ×1 ONLY — single graph writer
                 │  celery -B  │  embedded beat, 2 s flush
                 └──────┬──────┘
                        ▼
                 Neo4j  MERGE  →  INCR graph:version  →  XADD graph:deltas
```

**Replica constraints that are correctness requirements, not tuning:**

| workload | replicas | why |
|---|---|---|
| `graphd` | exactly 1 | single graph writer + embedded beat scheduler |
| `connectors` | exactly 1 | embedded beat — 2 replicas would double every scan |
| `agents` | 1 | in-process delta cursor |
| `tep-watcher` | 1 | holds open-alarm state |
| `extraction-*` | HPA 1→8 | stateless, scale on CPU |

**A concurrency lesson worth citing.** `extraction-text` originally ran
`-c 32` against a 2 GiB limit. Celery prefork forks one child per slot and each
child lazily builds its *own* FastEmbed model (~0.5 GiB resident), so the first
real ingestion burst put 32 models in one container and the kernel OOM-killed
it (exit 137). With `acks_late`, 28 in-flight tasks went to kombu's `unacked`
hash and would not have been redelivered until the visibility timeout expired.
Fix: `-c 4` with 4 GiB, and **scale out with the HPA, never up with `-c`** —
replicas bring their own memory, extra forks do not.

---

## A4.4 Kubernetes — GKE Autopilot

```
  Namespace: plantmind

  Deployment ×13     stateless services + celery workers
  StatefulSet ×3     neo4j, redis, minio  (PVC per pod)
  Job ×2             graph-init (constraints + vector index), tep-seed
  CronJob ×1         standards-scan
  HPA ×4             retrieval, gateway, extraction-text, resolution
  Ingress ×1         GCE L7, ManagedCertificate, static global IP
  ConfigMap ×4       plantmind-config + 3 file-backed
  Secret ×1          plantmind-secrets (from .env, sanitised)
  ServiceAccount ×1  plantmind-sa → Workload Identity → Vertex AI
```

**Configuration layering** — and a real trap. Both sources are mounted per pod:

```
    envFrom:
      - configMapRef: plantmind-config     ▸ applied first
      - secretRef:    plantmind-secrets    ▸ applied second — WINS
```

Any key present in both is decided by the Secret. `INTERVIEW_TEXT_MODE` lives
in both, so editing only the ConfigMap was a silent no-op until the Secret was
patched too.

**Two `.env` hazards handled at deploy time** (`scripts/deploy_gke.sh`):

1. `kubectl create secret --from-env-file` keeps inline comments verbatim, so
   `EMBEDDING_DIM=1536  # note` reached pydantic as `"1536  # note"` and every
   Python service crash-looped on `int_parsing`. Fixed by sanitising with
   `sed 's/[[:space:]]\{1,\}#.*$//'`.
2. `.env` carries **localhost** infra URLs for local dev. Layered over the
   ConfigMap they overrode the in-cluster service names. Fixed by excluding
   `NEO4J_URI|REDIS_URL|MINIO_ENDPOINT|RETRIEVAL_URL|AGENTS_URL` from the Secret.

**Workload Identity** — no service-account key file exists anywhere:

```
   KSA plantmind-sa ──bound──▶ GSA plantmind-vertex ──▶ roles/aiplatform.user
        (in-cluster)                (GCP IAM)              (Vertex AI)
```

---

## A4.5 REST — the gateway

FastAPI. The single public entry point and the **only** place auth is decided;
domain services are not internet-facing and stay oblivious.

```
   POST  /ask                    Q&A (JSON)
   POST  /ask/stream             Q&A (SSE token stream)
   POST  /documents/upload       multipart → staging → q_classify
   GET   /documents/{id}         presigned MinIO URL
   GET   /events/alerts          SSE, tails alerts:critical
   POST  /moc/assess             change-impact assessment
   GET   /graph/snapshot         node/edge slice for the explorer
   GET   /work-orders            drafts + decisions
   GET   /compliance             statutory digest
   POST  /permit                 permit-to-work generation
   GET   /health                 open — liveness/readiness
```

Auth is applied **per-router, not per-endpoint** — a new endpoint is protected
by default rather than by remembering to protect it:

```python
protected = [Depends(current_user)]
app.include_router(qa.router,        dependencies=protected)
app.include_router(documents.router, dependencies=protected)
...
app.include_router(system.router)    # /health must stay open
```

---

## A4.6 GraphQL — the retrieval read layer

Strawberry, mounted at `/graphql` on the retrieval service. REST is for
*actions*; GraphQL is for *reading the graph*, where clients need different
shapes of the same nodes and REST would need a new endpoint per shape.

```
   type Query {
     equipment(tag: String): [Equipment!]!
     failureModes(tag: String): [FailureMode!]!
     documents(ids: [ID!]): [Document!]!
     regulations(tag: String): [RegulationClause!]!
     workOrders(tag: String): [WorkOrder!]!
     procedures(tag: String): [Procedure!]!
     connections(tag: String, depth: Int): [Connection!]!
   }
```

Design constraint held throughout: **every resolver delegates to the existing
`GraphQLReader` Neo4j reads — no new Cypher was written for this layer.** The
GraphQL surface is a projection of queries the service already had, so it
cannot drift from REST behaviour or introduce an unreviewed query pattern.

```
             REST                      GraphQL
    ┌────────────────────┐    ┌──────────────────────┐
    │ actions, streaming │    │ typed graph reads    │
    │ upload, ask, SSE   │    │ client picks shape   │
    │ gateway :8000      │    │ retrieval :8001      │
    └─────────┬──────────┘    └──────────┬───────────┘
              └──────────┬───────────────┘
                         ▼
                  GraphReader (Cypher)
                         ▼
                       Neo4j
```

---

## A4.7 Data stores

| store | role | why this one |
|---|---|---|
| **Neo4j 5** | property graph + native vector index | one store answers both "what connects to what" (Cypher traversal) and "what reads like this" (ANN over 1536-d chunk embeddings) — no separate vector DB to keep in sync |
| **Redis 7** | broker, streams, cache, locks | already required as the Celery broker; streams give a durable replayable event log without adding Kafka |
| **MinIO** | raw document blobs | S3-compatible, self-hosted; browser fetches via presigned URLs so bytes never transit the gateway |
| **Timescale** | historian time-series | hypertable for simulation tags; external managed instance |
| **Supabase** | auth + profiles + conversations | Postgres with RLS; issues the JWTs the gateway verifies |

---

## A4.8 Why this shape

- **One writer.** All graph mutation funnels through `graphd` with `-c 1` and a
  Redis mutex. Concurrent `MERGE` on the same entity from several workers is
  the fastest way to corrupt a knowledge graph; making it structurally
  impossible was cheaper than making it safe.
- **Queue per cost class.** A 30 s vision extraction and a 200 ms table parse
  do not belong in the same pool. Separate queues let each scale on its own
  HPA and let `prefetch_multiplier=1` stop slow work from starving fast work.
- **Streams over callbacks.** `graph:deltas` and `alerts:critical` are durable
  and replayable, so a consumer that restarts resumes from its `cursor:` rather
  than losing events — and the UI attaches with SSE without any polling.
- **Auth at exactly one edge.** The frontend can only *attach* a token; only
  the gateway can decide it is real. Everything behind it is a private network.
