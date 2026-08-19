#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# PlantMind → GKE, one script.
#
# Pulls everything it can from .env and ui/.env (project, region, supabase,
# passwords, secrets). You DON'T need a domain: if you don't pass UI_DOMAIN /
# API_DOMAIN, it reserves a static IP and uses nip.io magic DNS
# (ui.<IP>.nip.io / api.<IP>.nip.io) which resolves to that IP automatically —
# so you still get HTTPS (needed for the mic + Supabase) with zero DNS setup.
#
#   ./scripts/deploy_gke.sh                       # nip.io, no domain needed
#   UI_DOMAIN=app.co API_DOMAIN=api.co ./scripts/deploy_gke.sh   # your own domain
#
# Idempotent — safe to re-run. Run stages individually if you like:
#   ./scripts/deploy_gke.sh cluster|wi|images|config|secrets|apply
# (no arg = all stages in order)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."           # repo root

getenv() { grep -E "^$1=" "${2:-.env}" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'\''\r'; }

# ── derived from .env / ui/.env ──────────────────────────────────────────────
PROJECT="${PROJECT:-$(getenv GCP_PROJECT)}"
REGION="${REGION:-$(getenv VERTEX_REGION)}"; REGION="${REGION:-us-central1}"
CLUSTER="${CLUSTER:-plantmind}"
REGISTRY="$REGION-docker.pkg.dev/$PROJECT/plantmind"
TAG="${TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo latest)}"
SA="plantmind-vertex@$PROJECT.iam.gserviceaccount.com"
VITE_SUPABASE_URL="$(getenv VITE_SUPABASE_URL ui/.env)"
VITE_SUPABASE_ANON_KEY="$(getenv VITE_SUPABASE_ANON_KEY ui/.env)"

[ -n "$PROJECT" ] || { echo "GCP_PROJECT not found in .env"; exit 1; }
gcloud config set project "$PROJECT" >/dev/null 2>&1 || true

# ── reserve the static IP and settle the two hostnames ───────────────────────
# Runs once, lazily; every stage that needs the domains calls it. If you passed
# your own UI_DOMAIN/API_DOMAIN it just reserves the IP for you to point them at;
# otherwise it derives nip.io names from the IP (no DNS records needed).
_resolved=""
resolve_domains() {
  [ -n "$_resolved" ] && return 0
  gcloud services enable compute.googleapis.com >/dev/null 2>&1 || true
  gcloud compute addresses describe plantmind-ip --global >/dev/null 2>&1 \
    || gcloud compute addresses create plantmind-ip --global
  IP="$(gcloud compute addresses describe plantmind-ip --global --format='value(address)')"
  if [ -z "${UI_DOMAIN:-}" ] || [ -z "${API_DOMAIN:-}" ]; then
    UI_DOMAIN="ui.${IP}.nip.io"
    API_DOMAIN="api.${IP}.nip.io"
    NIPIO=1
  fi
  _resolved=1
  echo "ip=$IP  ui=$UI_DOMAIN  api=$API_DOMAIN  (nip.io=${NIPIO:-0})"
}

echo "project=$PROJECT region=$REGION cluster=$CLUSTER tag=$TAG registry=$REGISTRY"

# ── stages ───────────────────────────────────────────────────────────────────
stage_cluster() {
  echo "== [1] APIs, cluster, Artifact Registry =="
  gcloud services enable container.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com compute.googleapis.com
  gcloud container clusters describe "$CLUSTER" --region "$REGION" >/dev/null 2>&1 \
    || gcloud container clusters create-auto "$CLUSTER" --region "$REGION"
  gcloud artifacts repositories describe plantmind --location "$REGION" >/dev/null 2>&1 \
    || gcloud artifacts repositories create plantmind --repository-format=docker --location "$REGION"
  gcloud auth configure-docker "$REGION-docker.pkg.dev" -q
  gcloud container clusters get-credentials "$CLUSTER" --region "$REGION"
}

stage_wi() {
  echo "== [2] Workload Identity for Vertex =="
  gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 \
    || gcloud iam service-accounts create plantmind-vertex
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$SA" --role="roles/aiplatform.user" --condition=None >/dev/null
  gcloud iam service-accounts add-iam-policy-binding "$SA" \
    --role="roles/iam.workloadIdentityUser" \
    --member="serviceAccount:$PROJECT.svc.id.goog[plantmind/plantmind-sa]" >/dev/null
}

stage_images() {
  resolve_domains
  echo "== [3] build + push images (UI baked with https://$API_DOMAIN) =="
  REGISTRY="$REGISTRY" TAG="$TAG" \
  VITE_GATEWAY_URL="https://$API_DOMAIN" \
  VITE_SUPABASE_URL="$VITE_SUPABASE_URL" \
  VITE_SUPABASE_ANON_KEY="$VITE_SUPABASE_ANON_KEY" \
  VITE_INTERVIEW_URL="https://$API_DOMAIN" \
    ./k8s/build-and-push.sh
  ( cd k8s
    for i in gateway retrieval agents diagnostics historian ingestion extraction \
             resolution graphd connectors interview simulation seed ui; do
      kustomize edit set image "plantmind-$i=$REGISTRY/plantmind-$i:$TAG"
    done )
}

stage_config() {
  resolve_domains
  echo "== [4/5] fill manifest placeholders =="
  sed -i "s#REPLACE_WITH_GCP_PROJECT_ID#$PROJECT#g" k8s/01-config.yaml k8s/50-serviceaccount.yaml
  sed -i "s#https://REPLACE_WITH_UI_DOMAIN#https://$UI_DOMAIN#g" k8s/01-config.yaml
  sed -i "s#MINIO_PUBLIC_ENDPOINT: .*#MINIO_PUBLIC_ENDPOINT: \"https://$API_DOMAIN\"#" k8s/01-config.yaml
  sed -i "s#ui.example.com#$UI_DOMAIN#g; s#api.example.com#$API_DOMAIN#g" k8s/51-ingress.yaml
}

stage_secrets() {
  echo "== [6] namespace + secret + file configmaps =="
  if [ -z "$(getenv TURN_SECRET)" ]; then
    ts="$(openssl rand -hex 32)"
    if grep -qE "^TURN_SECRET=" .env; then sed -i "s#^TURN_SECRET=.*#TURN_SECRET=$ts#" .env
    else echo "TURN_SECRET=$ts" >> .env; fi
    echo "   generated TURN_SECRET in .env"
  fi
  kubectl create namespace plantmind --dry-run=client -o yaml | kubectl apply -f -
  kubectl -n plantmind create secret generic plantmind-secrets --from-env-file=.env \
    --dry-run=client -o yaml | kubectl apply -f -
  kubectl -n plantmind create configmap plantmind-envelopes  --from-file=tep_envelopes.json=config/tep_envelopes.json \
    --dry-run=client -o yaml | kubectl apply -f -
  kubectl -n plantmind create configmap plantmind-connectors --from-file=connectors.json=connectors.json \
    --dry-run=client -o yaml | kubectl apply -f -
  kubectl -n plantmind create configmap plantmind-neo4j-init --from-file=init.cypher=infra/neo4j/init.cypher \
    --dry-run=client -o yaml | kubectl apply -f -
}

stage_apply() {
  resolve_domains
  echo "== [7] deploy =="
  kubectl apply -k k8s/
  echo
  echo "   URLs:   https://$UI_DOMAIN   (UI)"
  echo "           https://$API_DOMAIN  (API)"
  if [ -z "${NIPIO:-}" ]; then
    echo "   DNS:    point A records for the two hosts at $IP"
  else
    echo "   DNS:    none needed — nip.io resolves $UI_DOMAIN/$API_DOMAIN to $IP"
  fi
  echo "   watch:  kubectl -n plantmind get pods -w"
  echo "   cert:   kubectl -n plantmind describe managedcertificate plantmind-cert   # wait: Active (~15-60m)"
  echo "   verify: curl -s https://$API_DOMAIN/health"
}

case "${1:-all}" in
  cluster) stage_cluster ;;
  wi)      stage_wi ;;
  images)  stage_images ;;
  config)  stage_config ;;
  secrets) stage_secrets ;;
  apply)   stage_apply ;;
  all)     stage_cluster; stage_wi; stage_images; stage_config; stage_secrets; stage_apply ;;
  *) echo "unknown stage: $1"; exit 1 ;;
esac
echo "done: ${1:-all}"
