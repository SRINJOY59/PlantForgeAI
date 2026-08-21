# PlantForge AI — GKE Deployment Log & Runbook

A record of the actual deployment to GKE (Autopilot), the issues hit, and how
each was fixed — plus the success checks. Use it to redeploy or to onboard the
next person.

- **Cluster:** `plantmind` (GKE Autopilot), region `us-central1`
- **Registry:** `us-central1-docker.pkg.dev/<PROJECT>/plantmind`
- **Hostnames:** `ui.<IP>.nip.io` / `api.<IP>.nip.io` (nip.io magic DNS — no domain purchased)
- **LLM:** Vertex AI via **Workload Identity** (no key file)
- **Driver:** `scripts/deploy_gke.sh` (staged, idempotent)

---

## Steps applied (in order)

| Stage | Command | What it did |
|------|---------|-------------|
| 1 | `./scripts/deploy_gke.sh cluster` | enabled APIs, created the Autopilot cluster + Artifact Registry, `get-credentials` |
| 2 | `./scripts/deploy_gke.sh wi` | created GCP SA `plantmind-vertex`, granted `roles/aiplatform.user`, bound Workload Identity to KSA `plantmind-sa` |
| 3 | `./scripts/deploy_gke.sh images` | built + pushed all 14 images to Artifact Registry (UI baked with `https://api.<IP>.nip.io`) |
| 4 | `./scripts/deploy_gke.sh config` | reserved the static IP, derived nip.io hosts, `sed`-filled the manifests + pinned image tags |
| 5 | `./scripts/deploy_gke.sh secrets` | created the namespace, the Secret from `.env`, and the 3 file ConfigMaps |
| 6 | `./scripts/deploy_gke.sh apply` | `kubectl apply -k k8s/` — all workloads |

---

## Issues hit & fixes (the real journey)

### 1. `gke-gcloud-auth-plugin` not found (kubectl auth)
kubectl ≥ 1.26 needs this plugin to talk to GKE; it isn't bundled.
- **Fix:** installed it in the **Google Cloud SDK Shell (Run as Administrator)** — `gcloud components install gke-gcloud-auth-plugin` (without `--quiet`, which broke on the bundled Python), then added the SDK `bin` to PATH and set `USE_GKE_GCLOUD_AUTH_PLUGIN=True`.

### 2. `kustomize: command not found`
The deploy script pinned image tags with `kustomize edit set image`, but the standalone `kustomize` binary wasn't installed (`kubectl apply -k` has it built-in, but not `kustomize edit`).
- **Fix:** replaced the `kustomize edit` loop with a `sed` on `k8s/kustomization.yaml` (in `stage_config`) — no standalone `kustomize` needed.

### 3. coturn rejected by Autopilot
`kubectl apply` denied the coturn Deployment: Autopilot forbids `hostNetwork`, host ports, and custom node-selector labels.
- **Fix:** commented `70-coturn.yaml` out of `k8s/kustomization.yaml`. Voice interview is deferred (needs a **Standard** node pool for coturn); text-mode interview works without it.

### 4. `ImagePullBackOff` on every `plantmind-*` image
Public images (neo4j/redis/minio) pulled fine, but ours failed — the GKE node service account lacked Artifact Registry read.
- **Fix:**
  ```bash
  PROJECT=<PROJECT>; NUM=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
  gcloud projects add-iam-policy-binding $PROJECT \
    --member="serviceAccount:${NUM}-compute@developer.gserviceaccount.com" \
    --role="roles/artifactregistry.reader"
  kubectl -n plantmind delete pods --all   # force immediate re-pull
  ```

### 5. `neo4j-0` CrashLoopBackOff — `Unrecognized setting: PASSWORD`
Neo4j parses **every** `NEO4J_*` env var as a config setting, so the `NEO4J_PASSWORD` env (added only to build `NEO4J_AUTH`) was read as a bogus setting `PASSWORD` and strict validation refused to boot.
- **Fix:** renamed the env var to `NEO_PW` (no `NEO4J_` prefix) in `k8s/10-neo4j.yaml`, used it in `NEO4J_AUTH: "neo4j/$(NEO_PW)"` and the readiness probe. Re-applied.

### 6. Every Python service CrashLoopBackOff — `int_parsing` on `EMBEDDING_DIM`
`.env` has inline comments on numeric lines (`EMBEDDING_DIM=1536   # note`). Locally python-dotenv strips them, but `kubectl create secret --from-env-file` keeps the whole value, so pydantic got `"1536   # note"` and failed to parse the int → all services died on startup.
- **Fix:** `stage_secrets` now sanitizes `.env` into a temp file (`sed 's/[[:space:]]\{1,\}#.*$//'`) before creating the Secret, stripping trailing ` # comments` (a `#` inside a value is left alone). Recreated the Secret + `rollout restart deployment`.

### 7. `gateway`/`historian` connect to `localhost` (MinIO/Redis refused)
`.env` carries **localhost infra URLs** for local dev (`REDIS_URL`, `MINIO_ENDPOINT`, `NEO4J_URI`). They landed in the Secret, and since the Secret is layered *over* the ConfigMap in each pod's `envFrom`, the localhost values overrode the correct in-cluster service names → connection refused.
- **Fix:** `stage_secrets` now also excludes those infra URLs from the Secret (`grep -vE '^(NEO4J_URI|REDIS_URL|MINIO_ENDPOINT|RETRIEVAL_URL|AGENTS_URL)='`), so `01-config.yaml`'s service names (`redis`, `minio`, `neo4j`, …) win. Recreated Secret + `rollout restart deployment` + recreated the seed Jobs.

---

## Success checks

```bash
# 1. all pods Running (statefulsets first, then app pods; jobs Completed)
kubectl -n plantmind get pods

# 2. Neo4j healthy and seeded
kubectl -n plantmind get pods neo4j-0                     # 1/1 Running
kubectl -n plantmind get jobs                             # graph-init, tep-seed → Complete

# 3. ingress has the static IP + cert Active (15-60 min)
kubectl -n plantmind get ingress plantmind-ingress        # ADDRESS = <IP>
kubectl -n plantmind describe managedcertificate plantmind-cert   # Status: Active

# 4. API + UI reachable over HTTPS
curl -s https://api.<IP>.nip.io/health                    # {"status":"ok"}
#   open https://ui.<IP>.nip.io  and sign in

# 5. Vertex works via Workload Identity (no key)
kubectl -n plantmind logs deploy/retrieval | grep -iE "vertex|error" | tail
```

**Deployment is "done" when:** every pod is `Running`/`Completed`, the managed cert is `Active`, and `curl …/health` returns 200.

---

## Post-deploy notes

- **Supabase JWT** — ensure `SUPABASE_JWT_SECRET` is in `.env` (in the Secret) or the gateway runs open. After changing the Secret: `kubectl -n plantmind rollout restart deploy/gateway`.
- **Supabase schema** — run `supabase/schema.sql` in your Supabase project (worker role + RLS).
- **Historian** — `TIMESCALE_DSN` (Timescale Cloud) is set, so the historian + diagnostics are live.
- **Voice interview (coturn)** — to enable later: add a Standard node pool, label a node `plantmind.io/coturn=true`, open a firewall for udp:3478 + udp:49160-49200, set `TURN_URL`/`TURN_EXTERNAL_IP` in `k8s/01-config.yaml`, and re-enable `70-coturn.yaml`.
- **Redeploy after a code change:** `./scripts/deploy_gke.sh images && ./scripts/deploy_gke.sh config && kubectl apply -k k8s/ && kubectl -n plantmind rollout restart deploy`.

---

## Cost / teardown

```bash
# stop paying for it (delete everything)
gcloud container clusters delete plantmind --region us-central1
gcloud compute addresses delete plantmind-ip --global
```
