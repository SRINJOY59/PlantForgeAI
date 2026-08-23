# Appendix A6 — Cost Model

**Two kinds of number appear below.** Resource *quantities* are **measured**
from the live cluster (`kubectl get pods -o custom-columns=…resources.requests`)
and are exact. Unit *prices* are indicative GCP list rates for `us-central1`
and should be confirmed against the pricing calculator before being quoted as
figures — they move, and they vary by committed-use and free-tier status.

---

## A6.1 What GKE Autopilot actually bills

Autopilot does **not** bill for nodes. It bills for the sum of your pods'
**resource requests**, per second. This makes the cost model unusually direct:

```
                ┌────────────────────────────────────────────┐
                │   Cost  =  Σ requests × unit rate × hours   │
                └────────────────────────────────────────────┘

    NOT nodes.  NOT usage.  REQUESTS.

    → an over-requested pod costs exactly as much idle as it does busy
    → right-sizing requests IS the cost lever
```

---

## A6.2 Measured footprint (steady state)

One-shot Jobs (`graph-init`, `tep-seed`) and the CronJob are excluded — they
bill only while running.

```
  WORKLOAD              rep   CPU/pod   MEM/pod    CPU tot   MEM tot
  ────────────────────  ───   ───────   ───────    ───────   ────────
  extraction-text        1     1000m     4 GiB      1000m     4096 Mi
  tep-sim                1     1000m     1 GiB      1000m     1024 Mi
  retrieval              2      500m     1 GiB      1000m     2048 Mi
  extraction-wo          1      500m     3 GiB       500m     3072 Mi
  neo4j                  1      500m     2 GiB       500m     2048 Mi
  agents-api             2      250m     1 GiB       500m     2048 Mi
  gateway                2      250m   512 Mi        500m     1024 Mi
  extraction-pnid        1      250m     1 GiB       250m     1024 Mi
  resolution             1      250m     1 GiB       250m     1024 Mi
  interview              1      250m   512 Mi        250m      512 Mi
  agents                 1      200m     1 GiB       200m     1024 Mi
  diagnostics            1      200m   512 Mi        200m      512 Mi
  graphd                 1      200m   512 Mi        200m      512 Mi
  ingestion              1      200m   512 Mi        200m      512 Mi
  connectors             1      100m   512 Mi        100m      512 Mi
  historian              1      100m   256 Mi        100m      256 Mi
  minio                  1      100m   256 Mi        100m      256 Mi
  redis                  1      100m   256 Mi        100m      256 Mi
  tep-watcher            1      100m   256 Mi        100m      256 Mi
  ui                     2       50m    64 Mi        100m      128 Mi
  ────────────────────  ───   ───────   ───────    ───────   ────────
  TOTAL                  22                        7 150m    22 144 Mi
                                                 = 7.15 vCPU = 21.63 GiB
```

Storage and network, measured:

```
    PersistentVolumeClaims          Network
    ─────────────────────────       ────────────────────────────
    data-neo4j-0     20 GiB         1 × GCE L7 load balancer
    data-minio-0     20 GiB         1 × global static IP (in use)
    data-redis-0     10 GiB         1 × Google-managed certificate
    ─────────────────────────       2 hostnames (ui., api.)
    TOTAL            50 GiB         Artifact Registry: 22 images
```

---

## A6.3 Monthly infrastructure estimate

At 730 hours. Indicative `us-central1` list rates:

```
  ╔═══════════════════════════════════════════════════════════════════╗
  ║  COMPONENT           QUANTITY      RATE (indic.)      MONTHLY     ║
  ╠═══════════════════════════════════════════════════════════════════╣
  ║  Autopilot vCPU      7.15 vCPU     $0.0573/vCPU-hr     ~$299      ║
  ║  Autopilot memory   21.63 GiB      $0.00633/GiB-hr     ~$100      ║
  ║  ──────────────────────────────────────────────────────────────   ║
  ║  Compute subtotal                                      ~$399      ║
  ╠═══════════════════════════════════════════════════════════════════╣
  ║  Cluster mgmt fee    1 cluster     $0.10/hr = $73                 ║
  ║      less free tier                −$74.40 credit        ~$0      ║
  ╠═══════════════════════════════════════════════════════════════════╣
  ║  PD balanced         50 GiB        $0.10/GiB-mo           ~$5     ║
  ║  L7 load balancer    1 rule        $0.025/hr             ~$18     ║
  ║  Static IP           1, in use     (free while attached)   $0     ║
  ║  Artifact Registry   ~10 GB        $0.10/GB-mo            ~$1     ║
  ║  Egress              variable      $0.12/GiB            ~$1–10    ║
  ╠═══════════════════════════════════════════════════════════════════╣
  ║  INFRASTRUCTURE TOTAL                              ≈ $425/month   ║
  ╚═══════════════════════════════════════════════════════════════════╝
```

```
   Compute dominates — and inside compute, four pods dominate:

   extraction-text  ████████████████████  1.00 vCPU + 4 GiB   ~24%
   tep-sim          ████████████████      1.00 vCPU + 1 GiB   ~16%
   retrieval ×2     ████████████████      1.00 vCPU + 2 GiB   ~17%
   extraction-wo    ████████              0.50 vCPU + 3 GiB   ~12%
   everything else  ███████████████████   3.65 vCPU + 11 GiB  ~31%
```

---

## A6.4 LLM inference — the variable cost

Vertex AI, Gemini via Workload Identity. **Embeddings cost nothing**: FastEmbed
runs locally in-process (`EMBEDDING_BASE_URL=local`), which is why
`extraction-text` needs 4 GiB — memory is traded for API spend.

```
    Tier        Model                    Used for
    ────────    ─────────────────────    ─────────────────────────────────
    CHEAP       gemini-2.5-flash-lite    doc classification, follow-up
                                         condensing, eval judge
    MID         gemini-2.5-flash         extraction lanes, answer generation
    VISION      gemini-2.5-flash         P&ID, nameplates, charts, OCR
```

**Per-question model** (typical PathRAG answer):

```
    context assembled   ≈ 6 000 input tokens
    answer generated    ≈   600 output tokens

    cost ≈ 6000/1e6 × $0.30  +  600/1e6 × $2.50
         ≈ $0.0018            +  $0.0015
         ≈ $0.0033  per question          ← ~$3.30 per 1 000 questions
```

**Per-document ingestion** (one pass through classify → extract → resolve):

```
    short text / email      ~$0.005      ┐
    table (work orders)     ~$0.003      │  the 44-document seed corpus
    P&ID / image (vision)   ~$0.02       │  costs roughly $0.50–2.00
    100-page manual         ~$0.05–0.15  ┘  to ingest, once
```

Two mechanisms suppress the recurring bill materially:

```
   ┌─────────────────────────────────────────────────────────────┐
   │  Semantic answer cache    repeated/similar questions cost 0 │
   │  Extraction cache+lock    re-ingesting identical bytes      │
   │  cache:extract:<lane>:<h> short-circuits before any LLM call│
   │  Content-hash gate        duplicate documents never enter   │
   └─────────────────────────────────────────────────────────────┘
```

---

## A6.5 Scenarios

```
  ┌──────────────────────┬────────────┬────────────┬──────────────┐
  │                      │ HACKATHON  │  PILOT     │  PRODUCTION  │
  │                      │ 3-day demo │ 1 plant    │  multi-unit  │
  ├──────────────────────┼────────────┼────────────┼──────────────┤
  │ cluster hours        │   72 h     │   730 h    │    730 h     │
  │ questions / day      │    ~50     │    ~500    │    ~5 000    │
  │ documents ingested   │     44     │   ~2 000   │   ~50 000    │
  ├──────────────────────┼────────────┼────────────┼──────────────┤
  │ infrastructure       │    ~$42    │    ~$425   │  ~$900†      │
  │ LLM inference        │     ~$2    │     ~$60   │    ~$550     │
  ├──────────────────────┼────────────┼────────────┼──────────────┤
  │ TOTAL                │    ~$44    │    ~$485   │  ~$1 450     │
  │ per question         │      —     │   ~$0.032  │   ~$0.010    │
  └──────────────────────┴────────────┴────────────┴──────────────┘

  † HPA fan-out on extraction-text/retrieval + larger PVCs.
    Marginal cost per question FALLS with scale: infrastructure is
    fixed, and the answer cache hit rate rises as question volume grows.
```

---

## A6.6 Cost levers, in order of effect

```
  1  ▐████████████████▌  Delete the cluster between demos
                         gcloud container clusters delete plantmind \
                             --region us-central1
                         → $425/mo becomes ~$0. Biggest single lever by far.

  2  ▐██████████▌        Scale non-demo workloads to zero
                         tep-sim (1 vCPU!), diagnostics, historian,
                         tep-watcher, connectors ≈ 1.5 vCPU + 2 GiB reclaimed

  3  ▐████████▌          Right-size extraction-text between bursts
                         4 GiB is sized for ingestion concurrency, not for
                         idle. Scale to 0 when no corpus is being loaded.

  4  ▐██████▌            Drop HA pairs in non-production
                         retrieval, gateway, agents-api, ui are all ×2 for
                         availability. ×1 reclaims ~1.1 vCPU + 2.6 GiB.

  5  ▐████▌              Already done — keep it
                         · FastEmbed local     → $0 embedding API spend
                         · Answer cache        → repeat questions free
                         · Extraction cache    → re-ingest free
                         · Flash-Lite on cheap tier
                         · Rate limiting       → caps worst-case LLM bill
```

---

## A6.7 Costs outside GCP

Not in the totals above:

```
    Supabase          auth, profiles, conversations   free tier → $25/mo
    Timescale Cloud   historian hypertable            free tier → $50/mo
    Deepgram          voice STT/TTS (interview)       pay-per-minute
    Domain            none — nip.io magic DNS         $0
```

The `nip.io` choice is itself a cost decision: `ui.<IP>.nip.io` and
`api.<IP>.nip.io` resolve without registering or paying for a domain, and still
receive a real Google-managed TLS certificate.

---

## A6.8 Architectural decisions that were cost decisions

```
   ┌──────────────────────────┬──────────────────────────────────────┐
   │ DECISION                 │ COST CONSEQUENCE                     │
   ├──────────────────────────┼──────────────────────────────────────┤
   │ Neo4j native vector      │ no separate vector DB to run or pay  │
   │ index, not Pinecone      │ for; one store, one PVC              │
   ├──────────────────────────┼──────────────────────────────────────┤
   │ FastEmbed in-process     │ zero embedding API spend — paid for  │
   │                          │ in RAM (4 GiB on extraction-text)    │
   ├──────────────────────────┼──────────────────────────────────────┤
   │ Redis Streams, not Kafka │ broker already required; no extra    │
   │                          │ cluster, no extra PVCs               │
   ├──────────────────────────┼──────────────────────────────────────┤
   │ Rule-based mode router   │ no LLM call to decide strategy —     │
   │                          │ saves one round trip per question    │
   ├──────────────────────────┼──────────────────────────────────────┤
   │ Deterministic grounding  │ no second LLM call to grade the      │
   │                          │ answer's own provenance              │
   ├──────────────────────────┼──────────────────────────────────────┤
   │ Autopilot, not Standard  │ no node over-provisioning; billed on │
   │                          │ requests. Trade-off: node pools      │
   │                          │ cannot be modified, which is why     │
   │                          │ coturn could not be deployed         │
   ├──────────────────────────┼──────────────────────────────────────┤
   │ Tiered LLM routing       │ Flash-Lite for classification and    │
   │                          │ condensing; Flash reserved for       │
   │                          │ extraction and generation            │
   └──────────────────────────┴──────────────────────────────────────┘
```

---

## A6.9 Reproducing these numbers

```bash
# measured CPU / memory requests — what Autopilot bills
kubectl -n plantmind get pods \
  -o custom-columns='NAME:.metadata.name,CPU:.spec.containers[*].resources.requests.cpu,MEM:.spec.containers[*].resources.requests.memory'

# storage
kubectl -n plantmind get pvc

# live utilisation, to spot over-requested pods
kubectl -n plantmind top pods
```

Comparing `top pods` against the requests table is the fastest way to find
money being spent on headroom that is never used.
