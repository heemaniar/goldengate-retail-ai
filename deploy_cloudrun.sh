#!/usr/bin/env bash
# ── MallPulse — Cloud Run deploy script ──────────────────────────────────────
# Usage: bash deploy_cloudrun.sh
#
# Requires:
#   - gcloud CLI authenticated:  gcloud auth login && gcloud auth configure-docker us-central1-docker.pkg.dev
#   - Artifact Registry repo created (script creates it if missing)
#   - APIs enabled: Cloud Run, Artifact Registry, Cloud Build
#     gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT="mallpulse-hackathon"
REGION="us-central1"
SERVICE="mallpulse"
REPO="mallpulse-repo"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/${SERVICE}"

# ── Load .env so we can pass vars to Cloud Run ────────────────────────────────
if [[ -f .env ]]; then
  export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi

echo "▶ Project : ${PROJECT}"
echo "▶ Region  : ${REGION}"
echo "▶ Image   : ${IMAGE}"
echo ""

# ── 1. Ensure Artifact Registry repo exists ───────────────────────────────────
echo "1/4  Ensuring Artifact Registry repo..."
gcloud artifacts repositories describe "${REPO}" \
  --project="${PROJECT}" --location="${REGION}" --format="value(name)" 2>/dev/null \
  || gcloud artifacts repositories create "${REPO}" \
       --project="${PROJECT}" \
       --location="${REGION}" \
       --repository-format=docker \
       --description="MallPulse container images"

# ── 2. Build & push image via Cloud Build (no local Docker needed) ────────────
echo ""
echo "2/4  Building image with Cloud Build..."
gcloud builds submit . \
  --project="${PROJECT}" \
  --tag="${IMAGE}" \
  --machine-type=E2_HIGHCPU_8

# ── 3. Deploy to Cloud Run ────────────────────────────────────────────────────
echo ""
echo "3/4  Deploying to Cloud Run..."
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --image="${IMAGE}" \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300 \
  --concurrency=10 \
  --min-instances=0 \
  --max-instances=3 \
  --set-env-vars="\
GOOGLE_GENAI_USE_VERTEXAI=${GOOGLE_GENAI_USE_VERTEXAI:-1},\
GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT:-mallpulse-hackathon},\
GOOGLE_CLOUD_LOCATION=${GOOGLE_CLOUD_LOCATION:-us-central1},\
GCP_PROJECT=${GCP_PROJECT:-mallpulse-hackathon},\
GCP_REGION=${GCP_REGION:-us-central1},\
BQ_DATASET=${BQ_DATASET:-mallpulse_core},\
LOOKER_STUDIO_URL=${LOOKER_STUDIO_URL:-},\
PG_HOST=${PG_HOST:-},\
PG_USER=${PG_USER:-postgres},\
PG_PORT=${PG_PORT:-5432},\
PG_DB=${PG_DB:-mallpulse},\
FIVETRAN_API_KEY=${FIVETRAN_API_KEY:-},\
FIVETRAN_API_SECRET=${FIVETRAN_API_SECRET:-},\
FIVETRAN_CONNECTOR_ID=${FIVETRAN_CONNECTOR_ID:-},\
PG_PWD=${PG_PWD:-}"

# ── 4. Get the service URL ────────────────────────────────────────────────────
echo ""
echo "4/4  Done! Service URL:"
gcloud run services describe "${SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --format="value(status.url)"
