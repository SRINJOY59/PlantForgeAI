# PlantMind on GKE — deployment runbook

This deploys the whole PlantMind stack (Neo4j, Redis, MinIO, the FastAPI
services, the Celery workers, the TEP simulator, the UI, and the standards
CronJob) to a GKE cluster. Vertex AI auth is handled by **Workload Identity**
— no key files.

External dependencies stay external: **Supabase** (auth), and optionally
**Timescale Cloud** (historian) via `TIMESCALE_DSN`.

---

## 0. Prerequisites

- `gcloud`, `kubectl`, `kustomize` (or `kubectl` ≥ 1.27 with `-k`), and Docker.
- Your `.env` filled in (Gemini/Deepgram/Slack keys, `NEO4J_PASSWORD`,
  `MINIO_PASSWORD`, `SUPABASE_JWT_SECRET`, optional `TIMESCALE_DSN`).
- A domain you can point at a static IP (for the UI and the API).

Set shared variables (used throughout):

```bash
export PROJECT=your-gcp-project-id
export REGION=us-central1
export CLUSTER=plantmind
export REGISTRY=$REGION-docker.pkg.dev/$PROJECT/plantmind
gcloud config set project $PROJECT
```

---

## 1. Cluster + Artifact Registry

```bash
gcloud services enable container.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com

# GKE Autopilot (simplest) with Workload Identity on by default:
gcloud container clusters create-auto $CLUSTER --region $REGION

gcloud artifacts repositories create plantmind --repository-format=docker --location=$REGION
gcloud auth configure-docker $REGION-docker.pkg.dev
gcloud container clusters get-credentials $CLUSTER --region $REGION
```

> Autopilot ignores CPU/memory `limits` you set below and right-sizes from
> `requests` — that's fine. If you use a Standard cluster instead, size the node
> pool for the whole stack (≈ 8 vCPU / 32 GB is a sensible floor) and create it
> with `--workload-pool=$PROJECT.svc.id.goog`.

---

## 2. Vertex auth via Workload Identity

Create a GCP service account, grant it Vertex, and bind it to the in-cluster
`plantmind-sa`:

```bash
gcloud iam service-accounts create plantmind-vertex

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:plantmind-vertex@$PROJECT.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

# allow the k8s SA (namespace plantmind, name plantmind-sa) to impersonate it
gcloud iam service-accounts add-iam-policy-binding \
  plantmind-vertex@$PROJECT.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:$PROJECT.svc.id.goog[plantmind/plantmind-sa]"
```

Then set the GCP SA email in `k8s/50-serviceaccount.yaml` (replace
`REPLACE_WITH_GCP_PROJECT_ID`).

---

## 3. Build & push images

```bash
export TAG=$(git rev-parse --short HEAD)
export VITE_GATEWAY_URL=https://api.example.com          # your API host (step 6)
export VITE_SUPABASE_URL=https://xxxx.supabase.co
export VITE_SUPABASE_ANON_KEY=eyJ...                     # supabase anon key
export VITE_INTERVIEW_URL=https://api.example.com        # or a dedicated host
./k8s/build-and-push.sh
```

Point the manifests at your registry + tag:

```bash
cd k8s
for i in gateway retrieval agents diagnostics historian ingestion extraction \
         resolution graphd connectors interview simulation seed ui; do
  kustomize edit set image plantmind-$i=$REGISTRY/plantmind-$i:$TAG
done
cd ..
```

---

## 4. Fill in the placeholders

- `k8s/01-config.yaml`: `GCP_PROJECT` / `GOOGLE_CLOUD_PROJECT` = your project id;
  `CORS_ORIGINS` = your UI URL; `MINIO_PUBLIC_ENDPOINT` = your API host (MinIO is
  proxied through the gateway's `/documents/*/url`, so this is the API origin).
- `k8s/50-serviceaccount.yaml`: the GCP SA email (step 2).
- `k8s/51-ingress.yaml`: your real `ui.` and `api.` hosts (in `ManagedCertificate`
  **and** the `Ingress` rules).

---

## 5. Secret + file ConfigMaps from the repo

Created out-of-band so secrets never live in the repo and the config files stay
in their source locations (run from the repo root):

```bash
kubectl create namespace plantmind --dry-run=client -o yaml | kubectl apply -f -

# secrets from .env (pods read only the keys they need; extras are harmless)
kubectl -n plantmind create secret generic plantmind-secrets --from-env-file=.env

# the three file-backed ConfigMaps the manifests mount
kubectl -n plantmind create configmap plantmind-envelopes  --from-file=tep_envelopes.json=config/tep_envelopes.json
kubectl -n plantmind create configmap plantmind-connectors --from-file=connectors.json=connectors.json
kubectl -n plantmind create configmap plantmind-neo4j-init --from-file=init.cypher=infra/neo4j/init.cypher
```

> To update any of these later, append `--dry-run=client -o yaml | kubectl apply -f -`
> to the same command.

---

## 6. Reserve the static IP + DNS

```bash
gcloud compute addresses create plantmind-ip --global
gcloud compute addresses describe plantmind-ip --global --format='value(address)'
```

Create **A records** for `ui.example.com` and `api.example.com` pointing at that
IP. (The managed cert only goes Active once DNS resolves — allow 15–60 min.)

---

## 7. Deploy

```bash
kubectl apply -k k8s/
```

Order is handled for you: the app pods wait on Neo4j/Redis readiness, and the
`graph-init` / `tep-seed` Jobs retry until Neo4j is up. Watch it come up:

```bash
kubectl -n plantmind get pods -w
kubectl -n plantmind get ingress plantmind-ingress          # EXTERNAL IP + hosts
kubectl -n plantmind describe managedcertificate plantmind-cert   # Status: Active?
```

Re-running the init Jobs after a change:

```bash
kubectl -n plantmind delete job graph-init tep-seed --ignore-not-found
kubectl apply -k k8s/
```

---

## 8. Verify

```bash
# API health (once the cert is Active)
curl -s https://api.example.com/health
# open https://ui.example.com and sign in (Supabase)
kubectl -n plantmind logs deploy/retrieval | tail
kubectl -n plantmind logs deploy/tep-sim | tail          # telemetry ticking
kubectl -n plantmind create job --from=cronjob/standards-scan standards-now   # run the scan on demand
```

---

## Notes & known limitations

- **Voice interview (WebRTC):** wired via a coturn TURN relay (`70-coturn.yaml`)
  — see the dedicated section below. Text mode works with no extra setup.
- **Historian / diagnostics** need `TIMESCALE_DSN` (Timescale Cloud). Leave it
  empty and both disable themselves cleanly; the rest of the stack runs.
- **FastEmbed model** lives in an `emptyDir`, so it re-downloads (~30 s) on pod
  restart. For instant restarts, swap it for a Filestore (RWX) PVC shared across
  the embedding pods.
- **Autoscaling** is CPU-based (`60-hpa.yaml`), replacing the compose
  `autoscaler`. For queue-depth scaling, add KEDA with a Redis-stream trigger.
- **`graphd` and `connectors` must stay at 1 replica** (single graph writer /
  embedded beat) — they're excluded from the HPAs on purpose.
- **Supabase** stays external; set `SUPABASE_JWT_SECRET` in the Secret so the
  gateway enforces auth in prod.

---

## Voice interview / TURN

The voice bot's audio is WebRTC media (UDP), which an L7 Ingress can't carry, so
both peers relay through a coturn TURN server. The app side is already wired: the
interview backend mints time-limited TURN credentials from a shared secret and
serves them at `/api/turn`; the browser fetches them and both peers relay
through the same server. You provide coturn a reachable public address.

Because TURN needs a wide UDP relay-port range on the public internet, coturn
runs with `hostNetwork` on a dedicated node (Autopilot forbids `hostNetwork`, so
this needs a **Standard** node — add a small node pool if your cluster is
Autopilot):

```bash
# 1. a node for coturn (Standard pool; nodes get an external IP by default)
gcloud container node-pools create turn --cluster $CLUSTER --region $REGION \
  --num-nodes 1 --machine-type e2-small
kubectl get nodes -o wide                      # note a turn-pool node NAME + EXTERNAL-IP
kubectl label node <NODE> plantmind.io/coturn=true

# 2. firewall: open the TURN ports to that node
gcloud compute firewall-rules create plantmind-turn \
  --allow udp:3478,tcp:3478,udp:49160-49200 --direction INGRESS --source-ranges 0.0.0.0/0

# 3. a strong shared secret in .env BEFORE you create the Secret (step 5)
echo "TURN_SECRET=$(openssl rand -hex 32)" >> .env   # or edit the existing line
```

Then set, in `k8s/01-config.yaml`:
- `TURN_EXTERNAL_IP` = that node's `EXTERNAL-IP`
- `TURN_URL` = `turn:<that IP>:3478` (or a DNS name pointing at it)

Apply, and confirm: open the interview, start voice, and check
`kubectl -n plantmind logs deploy/coturn` shows an allocation when you connect.
`curl https://api.example.com/api/turn` should return an `iceServers` list with a
`turn:` entry and a fresh credential.

> **Verify on the live cluster.** WebRTC only proves out over a real network —
> this can't be tested from a laptop or in CI. If media doesn't flow, the usual
> causes are the firewall range, a wrong `TURN_EXTERNAL_IP`, or a node without a
> public IP. Prefer not to run coturn? Point `TURN_URL`/`TURN_SECRET` at a
> managed TURN (Twilio, Cloudflare Calls, Metered) and delete `70-coturn.yaml` —
> the app wiring is identical.
