# PlantForge AI — Cost Model

Measured from the running `plantmind` GKE Autopilot cluster (`us-central1`),
not estimated from the manifests. Quantities are real; **unit prices are list
prices and must be re-checked** against the
[GCP pricing calculator](https://cloud.google.com/products/calculator) before
anyone quotes them — they move, and this file does not.

---

## 1. Where the money goes

```
                          ┌──────────────────────────────────────┐
   browser ──── HTTPS ───▶│  Global External ALB                 │  $18.25/mo
                          │  2 forwarding rules (:80, :443)      │  ← fixed cost,
                          │  + managed TLS cert (free)           │    load-independent
                          │  + static IP 8.233.53.227 (free)     │
                          └──────────────┬───────────────────────┘
                                         │
                    ui.<ip>.nip.io ──────┤────── api.<ip>.nip.io
                                         │        └─ /interview ─▶ interview svc
                                         ▼
      ┌──────────────────────────────────────────────────────────────────┐
      │  GKE AUTOPILOT — billed on POD REQUESTS, not node size           │
      │  24 pods · 7.15 vCPU · 21.62 GiB                    $309.96/mo   │
      │                                                                  │
      │  ┌────────────────┬──────────┬─────────┬──────────────────────┐  │
      │  │ pod            │ vCPU     │ memory  │ $/mo   │ needed for  │  │
      │  ├────────────────┼──────────┼─────────┼────────┼─────────────┤  │
      │  │ extraction-text│  1.00    │ 4.0 GiB │ 46.86  │ ingest only │  │
      │  │ tep-sim        │  1.00    │ 1.0 GiB │ 36.08  │ sim demo    │  │
      │  │ extraction-wo  │  0.50    │ 3.0 GiB │ 27.02  │ ingest only │  │
      │  │ neo4j-0        │  0.50    │ 2.0 GiB │ 23.43  │ ALWAYS      │  │
      │  │ retrieval ×2   │  1.00    │ 2.0 GiB │ 39.67  │ ALWAYS      │  │
      │  │ agents-api ×2  │  0.50    │ 2.0 GiB │ 23.43  │ ALWAYS      │  │
      │  │ gateway ×2     │  0.50    │ 1.0 GiB │ 19.83  │ ALWAYS      │  │
      │  │ 15 others      │  2.15    │ 6.6 GiB │ 93.64  │ mixed       │  │
      │  └────────────────┴──────────┴─────────┴────────┴─────────────┘  │
      │                                                                  │
      │  + cluster management fee            $73/mo  ── FREE for the     │
      │    ($0.10/hr)                                  first cluster     │
      └───────┬──────────────────────────────────────────────────────────┘
              │
              ├──▶ Persistent Disks  50 GiB pd-balanced          $5.00/mo
              │      neo4j 20 · minio 20 · redis 10
              │
              ├──▶ Artifact Registry  ~1.6 GB, 63 versions       $0.11/mo
              │      (0.5 GB free tier)
              │
              └──▶ Vertex AI (Gemini 2.5 Flash / Flash-Lite)   PER TOKEN
                     ↑ the only line that scales with USE, not with UPTIME

   OUTSIDE GCP (separate bills, free tiers cover a hackathon):
     Supabase (auth)  ·  Timescale Cloud (historian)  ·  Deepgram (voice STT/TTS)
```

---

## 2. Monthly run-rate

```
  Autopilot vCPU   $232.27  ███████████████████████████████████  70%
  Autopilot memory  $77.69  ████████████                         23%
  Load balancer     $18.25  ███                                   5%
  Persistent disks   $5.00  █                                     2%
  Artifact Registry  $0.11                                       <1%
                   ────────
  INFRA TOTAL      $333.32/mo   ≈ $10.96/day   ≈ $0.46/hour
```

**The shape of this matters more than the total: ~93% is compute that bills
while idle.** An unused cluster costs almost exactly what a busy one does.
Vertex AI — the part that actually does the work — is a rounding error next to
the machines waiting to run it.

### One-off ingestion (44 documents → 764 nodes / 1054 edges)

Order of magnitude only — this was not metered directly, it is inferred from
the pipeline's call pattern (classify + extract per chunk + relation batches):

```
  ~1–3M input tokens  @ $0.30/M   ≈ $0.30–0.90
  ~0.1–0.3M output    @ $2.50/M   ≈ $0.25–0.75
                                    ─────────────
  full corpus re-ingest            ≈ $1–2 total
```

Re-ingesting everything from scratch costs less than **four hours of cluster
idle time**. Optimising the LLM spend here would be optimising the wrong thing.

---

## 3. Levers, largest first

```
  ┌──────────────────────────────────────────────┬──────────┬──────────────┐
  │ action                                       │ saves/mo │ costs you    │
  ├──────────────────────────────────────────────┼──────────┼──────────────┤
  │ Delete cluster between demo days             │ ~$333    │ 20 min setup │
  │   gcloud container clusters delete plantmind │          │ to rebuild   │
  │   --region us-central1                       │          │              │
  ├──────────────────────────────────────────────┼──────────┼──────────────┤
  │ Scale ingestion to 0 when not ingesting      │  $73.88  │ nothing —    │
  │   kubectl -n plantmind scale deploy/…        │          │ scale up for │
  │   extraction-text extraction-wo --replicas=0 │          │ new docs     │
  ├──────────────────────────────────────────────┼──────────┼──────────────┤
  │ HPA minReplicas 2 → 1 (retrieval, gateway,   │  $41.47  │ no HA, one   │
  │   agents-api) in k8s/60-hpa.yaml             │          │ cold pod on  │
  │                                              │          │ a restart    │
  ├──────────────────────────────────────────────┼──────────┼──────────────┤
  │ Scale tep-sim to 0 unless demoing simulation │  $36.08  │ Simulation   │
  │                                              │          │ page is dead │
  ├──────────────────────────────────────────────┼──────────┼──────────────┤
  │ Prune old Artifact Registry tags (63 vers.)  │   $0.11  │ no rollback  │
  │                                              │          │ ← not worth  │
  │                                              │          │   the risk   │
  └──────────────────────────────────────────────┴──────────┴──────────────┘

  Demo-day posture (everything but ingest + sim):     ~$223/mo  ≈ $7.35/day
  Judging-window only (8 h, then delete cluster):     ~$3.70 for the day
```

---

## 4. Why `extraction-text` is the most expensive pod

It is 1 vCPU / 4 GiB because it has to be. Celery prefork forks one child per
concurrency slot and **every child builds its own FastEmbed model** (~0.5 GiB
resident) — the singleton in `plantmind_core.llm.embeddings` is per-process,
not per-worker. At the original `-c 32` in a 2 GiB container the first real
inbox burst OOM-killed it (exit 137) and stranded 28 acks-late tasks in
kombu's `unacked` hash for a visibility timeout.

The fix was to cap concurrency at 4 and size memory to match, then scale
*out* with the HPA (`maxReplicas: 8`) rather than *up* with `-c`. Replicas
bring their own memory; extra forks do not. That trade is why this pod is
expensive at rest and why setting it to `--replicas=0` between ingests is the
single cheapest saving available.

---

## 5. What is NOT billed here

| Item | Why free |
|---|---|
| Managed TLS certificate | Google-managed certs cost nothing |
| Static IP `8.233.53.227` | External IPs are free while attached to a forwarding rule |
| Firewall rule `allow-webrtc-udp-plantmind` | VPC firewall rules are free |
| GKE cluster management fee | First cluster is covered by the GKE free tier credit |
| coturn / TURN relay | Not deployed — Autopilot node pools "cannot be accessed or modified", so voice currently runs STUN-only on a direct path |
