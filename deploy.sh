#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy.sh — Deploy the multi-agent Google system to Cloud Run
# Run once per environment. Re-run safely (idempotent gcloud calls).
# Prerequisites: gcloud CLI installed and authenticated.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── 0. CONFIGURE THESE ───────────────────────────────────────────────────────
PROJECT_ID="your-gcp-project-id"       # ← replace
REGION="us-central1"
SERVICE_NAME="multi-agent-google"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"
ALLOYDB_CLUSTER="agents-cluster"
ALLOYDB_INSTANCE="agents-instance"
ALLOYDB_DB="agents"
ALLOYDB_USER="agents_user"
SA_NAME="multi-agent-sa"

echo "=== [1/10] Setting project ==="
gcloud config set project "${PROJECT_ID}"

echo "=== [2/10] Enable required APIs ==="
gcloud services enable \
  run.googleapis.com \
  alloydb.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  calendar-json.googleapis.com \
  tasks.googleapis.com \
  keep.googleapis.com \
  maps-backend.googleapis.com \
  --project="${PROJECT_ID}"

echo "=== [3/10] Create service account ==="
gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="Multi-Agent Service Account" \
  --project="${PROJECT_ID}" || true   # ignore if exists

SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant roles
for ROLE in \
  roles/alloydb.client \
  roles/secretmanager.secretAccessor \
  roles/aiplatform.user \
  roles/datastore.user; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" --quiet
done

echo "=== [4/10] Create AlloyDB cluster + instance (takes ~5 min) ==="
gcloud alloydb clusters create "${ALLOYDB_CLUSTER}" \
  --region="${REGION}" \
  --password="CHANGE_ME_DB_PASSWORD" \
  --project="${PROJECT_ID}" || true

gcloud alloydb instances create "${ALLOYDB_INSTANCE}" \
  --cluster="${ALLOYDB_CLUSTER}" \
  --region="${REGION}" \
  --instance-type=PRIMARY \
  --cpu-count=2 \
  --project="${PROJECT_ID}" || true

echo "=== [5/10] Store secrets in Secret Manager ==="
# Replace the placeholder values before running
echo -n "CHANGE_ME_DB_PASSWORD" | gcloud secrets create alloydb-password \
  --data-file=- --project="${PROJECT_ID}" || \
  echo -n "CHANGE_ME_DB_PASSWORD" | gcloud secrets versions add alloydb-password \
    --data-file=- --project="${PROJECT_ID}"

echo -n "YOUR_GOOGLE_MAPS_API_KEY" | gcloud secrets create maps-api-key \
  --data-file=- --project="${PROJECT_ID}" || \
  echo -n "YOUR_GOOGLE_MAPS_API_KEY" | gcloud secrets versions add maps-api-key \
    --data-file=- --project="${PROJECT_ID}"

# Upload service account key JSON for Google Workspace APIs
gcloud secrets create google-sa-key \
  --data-file="./google-sa-key.json" --project="${PROJECT_ID}" || \
  gcloud secrets versions add google-sa-key \
    --data-file="./google-sa-key.json" --project="${PROJECT_ID}"

echo "=== [6/10] Build and push Docker image ==="
gcloud builds submit --tag "${IMAGE}" --project="${PROJECT_ID}"

echo "=== [7/10] Get AlloyDB private IP ==="
ALLOYDB_IP=$(gcloud alloydb instances describe "${ALLOYDB_INSTANCE}" \
  --cluster="${ALLOYDB_CLUSTER}" --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --format="value(ipAddress)")
echo "AlloyDB IP: ${ALLOYDB_IP}"

echo "=== [8/10] Deploy to Cloud Run ==="
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --service-account="${SA_EMAIL}" \
  --memory=1Gi \
  --cpu=2 \
  --concurrency=80 \
  --min-instances=1 \
  --max-instances=10 \
  --set-env-vars="\
GCP_PROJECT_ID=${PROJECT_ID},\
GCP_REGION=${REGION},\
ALLOYDB_HOST=${ALLOYDB_IP},\
ALLOYDB_DB=${ALLOYDB_DB},\
ALLOYDB_USER=${ALLOYDB_USER}" \
  --set-secrets="\
ALLOYDB_PASSWORD=alloydb-password:latest,\
GOOGLE_MAPS_API_KEY=maps-api-key:latest,\
/secrets/google-sa-key.json=google-sa-key:latest" \
  --vpc-connector="projects/${PROJECT_ID}/locations/${REGION}/connectors/alloydb-connector" \
  --project="${PROJECT_ID}"

echo "=== [9/10] Run DB migrations ==="
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" --format="value(status.url)")
echo "Service URL: ${SERVICE_URL}"

echo "=== [10/10] Health check ==="
curl -sf "${SERVICE_URL}/health" && echo " — Service is healthy!"

echo ""
echo "✓ Deployment complete."
echo "  API base URL : ${SERVICE_URL}"
echo "  Chat endpoint: POST ${SERVICE_URL}/chat"
echo ""
echo "Example:"
echo "  curl -X POST ${SERVICE_URL}/chat \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"message\": \"Schedule a meeting tomorrow at 10am called Team Sync\", \"user_id\": \"user123\"}'"
