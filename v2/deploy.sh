#!/bin/bash
# ════════════════════════════════════════════════════════════
# Truth-Filtering Research Pipeline v2 — Deployment Script
# Deploys all stages to Google Cloud Run + Cloud Workflows
# ════════════════════════════════════════════════════════════
set -euo pipefail

# ─── Configuration ─────────────────────────────────────────
PROJECT="${GCP_PROJECT:-oladizz-research}"
REGION="${GCP_REGION:-us-central1}"
REPO="research-pipeline"
GEMINI_KEY="${GEMINI_API_KEY:?GEMINI_API_KEY must be set}"

echo "═══════════════════════════════════════════════════"
echo " Deploying Truth-Filtering Research Pipeline v2"
echo " Project: $PROJECT | Region: $REGION"
echo "═══════════════════════════════════════════════════"

# ─── Step 0: Enable required APIs ─────────────────────────
echo ""
echo "→ Enabling required Google Cloud APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudtasks.googleapis.com \
  firestore.googleapis.com \
  bigquery.googleapis.com \
  workflows.googleapis.com \
  cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  --project="$PROJECT" --quiet

# ─── Step 1: Create Artifact Registry repo ─────────────────
echo ""
echo "→ Creating Artifact Registry repository..."
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --project="$PROJECT" \
  --quiet 2>/dev/null || echo "  (repository already exists)"

REGISTRY="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}"

# ─── Step 2: Create Firestore database (if needed) ────────
echo ""
echo "→ Ensuring Firestore database exists..."
gcloud firestore databases create \
  --location="$REGION" \
  --project="$PROJECT" \
  --quiet 2>/dev/null || echo "  (database already exists)"

# ─── Step 3: Create BigQuery dataset ──────────────────────
echo ""
echo "→ Creating BigQuery dataset..."
bq mk --project_id="$PROJECT" --location="$REGION" \
  --dataset "research_history" 2>/dev/null || echo "  (dataset already exists)"

# ─── Step 4: Create GCS bucket for reports ─────────────────
echo ""
echo "→ Creating GCS bucket for reports..."
gsutil mb -p "$PROJECT" -l "$REGION" -c NEARLINE \
  "gs://${PROJECT}-reports" 2>/dev/null || echo "  (bucket already exists)"

# ─── Step 5: Build and deploy Stage 3 (Scraper Service) ───
# This is a SERVICE (always-on), not a JOB, because Cloud Tasks sends HTTP requests to it.
echo ""
echo "→ Building & deploying Stage 3 (Scraper Service)..."
gcloud builds submit ./stage3_scraper \
  --tag "${REGISTRY}/stage3-scraper" \
  --project="$PROJECT" --quiet

gcloud run deploy stage3-scraper \
  --image "${REGISTRY}/stage3-scraper" \
  --region "$REGION" \
  --project "$PROJECT" \
  --platform managed \
  --no-allow-unauthenticated \
  --memory 1Gi \
  --timeout 300 \
  --max-instances 100 \
  --set-env-vars "GCP_PROJECT=$PROJECT,GEMINI_API_KEY=$GEMINI_KEY" \
  --quiet

SCRAPER_URL=$(gcloud run services describe stage3-scraper \
  --region "$REGION" --project "$PROJECT" \
  --format="value(status.url)")
echo "  Scraper URL: $SCRAPER_URL"

# ─── Step 6: Build and deploy Cloud Run JOBS ──────────────
declare -A STAGES=(
  ["stage1-search"]="stage1_search"
  ["stage2-queue-builder"]="stage2_queue_builder"
  ["stage4-dedup"]="stage4_dedup"
  ["stage5-extract"]="stage5_extract"
  ["stage6-cluster"]="stage6_cluster"
  ["stage7-scoring"]="stage7_scoring"
  ["stage9-delivery"]="stage9_delivery"
)

for JOB_NAME in "${!STAGES[@]}"; do
  DIR="${STAGES[$JOB_NAME]}"
  echo ""
  echo "→ Building & deploying ${JOB_NAME}..."
  
  gcloud builds submit ./"$DIR" \
    --tag "${REGISTRY}/${JOB_NAME}" \
    --project="$PROJECT" --quiet
  
  # Create or update the Cloud Run job
  gcloud run jobs create "$JOB_NAME" \
    --image "${REGISTRY}/${JOB_NAME}" \
    --region "$REGION" \
    --project "$PROJECT" \
    --memory 2Gi \
    --cpu 1 \
    --task-timeout 3600 \
    --set-env-vars "GCP_PROJECT=$PROJECT,GCP_REGION=$REGION,GEMINI_API_KEY=$GEMINI_KEY,SCRAPER_SERVICE_URL=${SCRAPER_URL}/scrape" \
    --quiet 2>/dev/null || \
  gcloud run jobs update "$JOB_NAME" \
    --image "${REGISTRY}/${JOB_NAME}" \
    --region "$REGION" \
    --project "$PROJECT" \
    --memory 2Gi \
    --cpu 1 \
    --task-timeout 3600 \
    --set-env-vars "GCP_PROJECT=$PROJECT,GCP_REGION=$REGION,GEMINI_API_KEY=$GEMINI_KEY,SCRAPER_SERVICE_URL=${SCRAPER_URL}/scrape" \
    --quiet
done

# ─── Step 7: Deploy Cloud Workflow ─────────────────────────
echo ""
echo "→ Deploying Cloud Workflow..."
gcloud workflows deploy research-pipeline \
  --source=workflow.yaml \
  --location="$REGION" \
  --project="$PROJECT" \
  --quiet

# ─── Step 8: Create Cloud Scheduler (optional trigger) ─────
echo ""
echo "→ Creating Cloud Scheduler trigger (disabled by default)..."
# This creates a scheduler that you can enable when you want automated runs.
# By default it's paused — you trigger runs manually via:
#   gcloud workflows run research-pipeline --data='{"topic":"your topic here"}'
gcloud scheduler jobs create http research-pipeline-trigger \
  --schedule="0 6 * * 1" \
  --uri="https://workflowexecutions.googleapis.com/v1/projects/${PROJECT}/locations/${REGION}/workflows/research-pipeline/executions" \
  --http-method=POST \
  --message-body='{"argument":"{\"topic\":\"weekly research topic\"}"}' \
  --oauth-service-account-email="${PROJECT}@appspot.gserviceaccount.com" \
  --location="$REGION" \
  --project="$PROJECT" \
  --quiet 2>/dev/null || echo "  (scheduler job already exists)"

# Pause it by default
gcloud scheduler jobs pause research-pipeline-trigger \
  --location="$REGION" --project="$PROJECT" --quiet 2>/dev/null || true

# ─── Done ──────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo " ✅ Deployment Complete!"
echo ""
echo " To run the pipeline manually:"
echo "   gcloud workflows run research-pipeline \\"
echo "     --data='{\"topic\":\"your research topic\"}' \\"
echo "     --location=$REGION --project=$PROJECT"
echo ""
echo " To check status:"
echo "   gcloud workflows executions list research-pipeline \\"
echo "     --location=$REGION --project=$PROJECT"
echo "═══════════════════════════════════════════════════"
