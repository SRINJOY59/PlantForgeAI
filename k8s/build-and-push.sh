#!/usr/bin/env bash
# Build every PlantMind image and push it to Artifact Registry.
# Run from the repo root:  ./k8s/build-and-push.sh
#
# Required env (export or edit the defaults):
#   REGISTRY   - Artifact Registry path, e.g. us-central1-docker.pkg.dev/my-proj/plantmind
#   TAG        - image tag (default: git short sha, else "latest")
# UI build-time config (baked into the SPA - must be the PUBLIC urls):
#   VITE_GATEWAY_URL, VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY, VITE_INTERVIEW_URL
set -euo pipefail

REGISTRY="${REGISTRY:?set REGISTRY, e.g. us-central1-docker.pkg.dev/my-proj/plantmind}"
TAG="${TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo latest)}"

echo "Building images -> ${REGISTRY} (tag ${TAG})"

# service.Dockerfile images: one per SERVICE build-arg. The image name equals
# the SERVICE, and several deployments share an image (agents -> agents/
# agents-api/tep-watcher/standards-cron; extraction -> extraction-*).
SERVICES=(gateway retrieval agents diagnostics historian ingestion extraction resolution graphd connectors interview)
for svc in "${SERVICES[@]}"; do
  img="${REGISTRY}/plantmind-${svc}:${TAG}"
  echo "==> ${img}"
  docker build -f infra/docker/service.Dockerfile --build-arg "SERVICE=${svc}" -t "${img}" .
  docker push "${img}"
done

# simulation + seed have their own Dockerfiles
docker build -f infra/docker/simulation.Dockerfile -t "${REGISTRY}/plantmind-simulation:${TAG}" .
docker push "${REGISTRY}/plantmind-simulation:${TAG}"
docker build -f infra/docker/seed.Dockerfile -t "${REGISTRY}/plantmind-seed:${TAG}" .
docker push "${REGISTRY}/plantmind-seed:${TAG}"

# UI: VITE_* values are baked in at build time, so they must be set now.
docker build -f infra/docker/ui.Dockerfile \
  --build-arg "VITE_GATEWAY_URL=${VITE_GATEWAY_URL:?set VITE_GATEWAY_URL (public gateway https url)}" \
  --build-arg "VITE_SUPABASE_URL=${VITE_SUPABASE_URL:?set VITE_SUPABASE_URL}" \
  --build-arg "VITE_SUPABASE_ANON_KEY=${VITE_SUPABASE_ANON_KEY:?set VITE_SUPABASE_ANON_KEY}" \
  --build-arg "VITE_INTERVIEW_URL=${VITE_INTERVIEW_URL:-}" \
  -t "${REGISTRY}/plantmind-ui:${TAG}" .
docker push "${REGISTRY}/plantmind-ui:${TAG}"

echo "Done. Now set the tag in k8s/: cd k8s && for i in gateway retrieval agents diagnostics historian ingestion extraction resolution graphd connectors interview simulation seed ui; do kustomize edit set image plantmind-\$i=${REGISTRY}/plantmind-\$i:${TAG}; done"
