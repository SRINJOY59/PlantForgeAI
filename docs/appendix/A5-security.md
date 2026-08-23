# Appendix A5 — Security Posture

What was actually defended against, where the control lives, and what is
knowingly left open. Source of truth: `services/gateway/{auth,security,
ratelimit,deps}.py`, `supabase/schema.sql`, `libs/core/plantmind_core/`.

---

## A5.1 Trust boundary

Exactly one boundary. The frontend can only *attach* a token; only the gateway
can decide it is real. Everything behind it is a private network with no
internet route.

```
   ┌── UNTRUSTED ─────────────────────────────────────────────────┐
   │  browser · uploaded documents · connector sources · LLM output│
   └───────────────────────────┬──────────────────────────────────┘
                               │
   ════════════════════════════╪═══════════════ TRUST BOUNDARY ═══
                               ▼
                    ┌──────────────────────┐
                    │       GATEWAY        │
                    │  ① JWT verify        │
                    │  ② role gate         │
                    │  ③ rate limit        │
                    │  ④ security headers  │
                    │  ⑤ CORS allowlist    │
                    └──────────┬───────────┘
                               │
   ┌── TRUSTED (ClusterIP only, no Ingress) ──────────────────────┐
   │  retrieval · agents-api · graphd · neo4j · redis · minio     │
   │  …deliberately oblivious to auth: not internet-facing        │
   └──────────────────────────────────────────────────────────────┘
```

---

## A5.2 Threats addressed

### ① Unauthenticated API access

Supabase-issued JWT, verified HS256 with **audience and expiry both enforced**:

```python
jwt.decode(token, SUPABASE_JWT_SECRET,
           algorithms=["HS256"],           # pinned — no `alg: none`, no confusion
           audience="authenticated")       # audience checked, not just signature
```

Pinning `algorithms` is the control against **algorithm-confusion attacks**,
where a forged token declares `alg: none` or swaps HS/RS to trick the verifier.

### ② Privilege escalation via role claim

Five-tier hierarchy, applied **per router** so a new endpoint is protected by
default rather than by remembering:

```
   worker  <  operator  <  planner  <  engineer  <  admin
     │           │            │           │           │
   field      Ask/Alerts   +Connectors  +Graph      +Connectors write
   only       /Documents    read        Compliance   role management
                                        MoC/Interview
                                        upload
```

Two hardening details that matter:

- An **unknown or missing** `app_role` falls back to `operator`, never to
  something higher — a misconfigured Supabase claims hook cannot silently
  elevate a user.
- `worker` is rank 0, *below* `operator`, so every `require_role("operator")`
  gate naturally excludes field accounts. A field persona is provisioned
  deliberately, never fallen into.

### ③ Cross-tenant data access

Postgres **Row-Level Security** on every user-owned table:

```sql
alter table public.profiles enable row level security;

create policy "profiles are private to their owner"
    on public.profiles for all
    using      (auth.uid() = id)
    with check (auth.uid() = id);

create policy "admins can read all profiles"
    on public.profiles for select
    using ((auth.jwt() -> 'app_metadata' ->> 'app_role') = 'admin');
```

The admin policy reads the **JWT claim** rather than querying `profiles` — a
policy on `profiles` that queries `profiles` to decide access recurses
infinitely. Same treatment on `conversations` and `messages` (the latter
inherits its parent conversation's ownership). Helper functions are
`security definer` with a pinned `search_path = public`, which is the standard
defence against **search-path hijacking** of a definer function.

### ④ Remote code execution via task deserialisation

```python
task_serializer = "json"
accept_content  = ["json"]
```

Celery's default `pickle` transport turns any write access to Redis into
arbitrary code execution on every worker. JSON-only closes that path outright.

### ⑤ Stored XSS / content sniffing on uploaded documents

Uploads are arbitrary user files served back to a browser — the classic stored
XSS vector. Defence is layered:

```
  X-Content-Type-Options : nosniff
        an upload served as text/plain cannot be re-sniffed as HTML and run
  Content-Security-Policy: default-src 'none'; frame-ancestors 'none';
                           base-uri 'none'
        if a response is ever coerced into rendering, it can load nothing
  X-Frame-Options        : DENY          clickjacking
  Referrer-Policy        : no-referrer    doc_id/token never leaks in Referer
  Permissions-Policy     : geolocation=(), microphone=(), camera=()
```

The document viewer renders from a **`blob:` URL**, not from the API response
directly, so `frame-ancestors 'none'` does not break legitimate viewing.
Headers use `setdefault`, so a handler that deliberately sets its own wins.

### ⑥ CORS misconfiguration

```python
allow_origins     = cors_origins(settings.cors_origins)   # explicit allowlist
allow_credentials = False
allow_methods     = ["GET", "POST"]
allow_headers     = ["Authorization", "Content-Type"]
```

Bearer tokens ride in the `Authorization` header, never cookies. Not needing
credentialed CORS is what allows a **real allowlist** instead of the
`"*"`-with-credentials combination browsers forbid anyway.

### ⑦ Abuse / cost exhaustion

Fixed-window limiter keyed on the authenticated subject, in Redis:

```
    INCR ratelimit:<bucket>:<sub>
    if count == 1:  EXPIRE key window_s
    if count >  limit:  429 + Retry-After: TTL
```

Keyed on `sub` (not IP), so it survives NAT and cannot be evaded by rotating
addresses. Each LLM-backed route is a cost multiplier, which makes this a
billing control as much as an abuse control.

### ⑧ Credential exposure

| risk | control |
|---|---|
| SA key file on disk / in image | **Workload Identity** — KSA → GSA → `roles/aiplatform.user`. No key file exists anywhere. |
| secrets in git | `k8s/02-secret.example.yaml` is a template; the real Secret is created out-of-band from `.env` at deploy time |
| secrets in image layers | never baked; injected via `envFrom.secretRef` at runtime |
| TURN long-term password | coturn `use-auth-secret`: username is an expiry timestamp, credential is `HMAC-SHA1(secret, username)`. The browser receives a **1-hour credential, never the shared secret**. |

### ⑨ Fabricated provenance (LLM-specific)

The threat unique to this class of system: a model that **invents a citation**
is more dangerous than one that admits ignorance, because a fake `[doc:…]`
looks exactly as authoritative as a real one to an engineer about to open a
vessel.

Deterministic check, no second LLM call — cited ids are compared against the
ids actually placed in the context:

```
   cited ⊄ available   →  unverified  ▮ RED    ← fabricated provenance
   cited = ∅           →  general     ▮ AMBER  ← model knowledge, badged
   cited ⊆ available   →  documents   ▮ GREEN
```

### ⑩ Ingestion-side integrity

- `SET doc:<sha256> 1 NX` — atomic content-hash gate; concurrent ingests of
  identical bytes cannot both pass.
- A lane that fails *after* the gate calls `release_document()`, so a transient
  failure cannot permanently brick a file.
- Single graph writer (`graphd`, `-c 1`, Redis mutex) — concurrent `MERGE` on
  one entity cannot corrupt the graph.
- Unparseable buffer items land in `graphd:write_dlq` rather than being
  silently dropped.

---

## A5.3 Control map

```
  ┌────────────────────────────┬──────────────────────────────────────┐
  │ THREAT                     │ CONTROL                    WHERE     │
  ├────────────────────────────┼──────────────────────────────────────┤
  │ forged / replayed token    │ HS256 + aud + exp          auth.py   │
  │ alg-confusion              │ algorithms pinned          auth.py   │
  │ privilege escalation       │ role hierarchy, safe dflt  deps.py   │
  │ endpoint added unprotected │ per-router dependency      main.py   │
  │ cross-tenant read          │ Postgres RLS               schema.sql│
  │ RLS policy recursion       │ JWT claim, not table read  schema.sql│
  │ search-path hijack         │ security definer + pinned  schema.sql│
  │ pickle RCE                 │ json-only serializer       worker_app│
  │ stored XSS / sniffing      │ nosniff + CSP + blob: URL  security.py│
  │ clickjacking               │ X-Frame-Options DENY       security.py│
  │ CORS over-permission       │ allowlist, no credentials  main.py   │
  │ abuse / cost exhaustion    │ Redis fixed-window on sub  ratelimit │
  │ SA key leakage             │ Workload Identity          50-sa.yaml│
  │ TURN password leak         │ HMAC time-limited cred     turn.py   │
  │ fabricated citation        │ deterministic grounding    grounding │
  │ duplicate / partial ingest │ hash gate + release        service.py│
  │ graph corruption           │ single writer + mutex      graphd    │
  └────────────────────────────┴──────────────────────────────────────┘
```

---

## A5.4 Known gaps — stated, not hidden

An honest appendix names what is open. All four are deliberate and reversible.

1. **Auth can be disabled.** With `SUPABASE_JWT_SECRET` unset the gateway runs
   open and grants `engineer` so the demo works. This is an intentional escape
   hatch and it **announces itself in the logs**
   (`SUPABASE_JWT_SECRET unset - gateway is OPEN`). It must be set in any real
   deployment.

2. **Wide UDP ingress for WebRTC.** Firewall rule `allow-webrtc-udp-plantmind`
   opens `udp:32768-60999` from `0.0.0.0/0` to the GKE node tag. That is the
   ephemeral range `aiortc` binds from, and neither `SmallWebRTCConnection` nor
   `aioice` accepts a port-range constraint, so it cannot be narrowed without
   patching the stack. The tighter alternative is a TURN relay on fixed ports;
   until then this is a known, documented exposure that can be removed with one
   `gcloud` command.

3. **Prompt injection via ingested documents.** A malicious uploaded document
   could carry instructions aimed at the extraction LLM. Partially mitigated —
   extraction outputs are schema-constrained (Pydantic) rather than free text,
   and the grounding check catches fabricated citations — but there is no
   dedicated injection filter on document content.

4. **No audit log.** Role checks are enforced but not recorded. There is no
   tamper-evident trail of who asked what or who approved which work order,
   which a real plant deployment would require.
