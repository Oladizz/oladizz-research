#!/bin/bash
# GCP Setup Script
# Run this ONCE from the Google Cloud Shell to set up your Firestore, Queues, and Scheduler.

export GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
if [ -z "$GCP_PROJECT" ] || [ "$GCP_PROJECT" = "(unset)" ]; then
  export GCP_PROJECT="litetrack-1783858226"
fi
export REGION="us-central1"
export SA_EMAIL="firebase-adminsdk-fbsvc@litetrack-1783858226.iam.gserviceaccount.com"

echo "Setting up Google Cloud infrastructure for Oladizz Research Pipeline on project: $GCP_PROJECT..."

# 0. Grant required roles to Service Account (if needed)
echo "Granting roles to Service Account..."
gcloud projects add-iam-policy-binding $GCP_PROJECT \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/editor" || true

# 1. Enable Required Google Cloud APIs
echo "Enabling APIs (this takes a minute)..."
gcloud services enable \
  run.googleapis.com \
  cloudtasks.googleapis.com \
  firestore.googleapis.com \
  workflows.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com

# 2. Create the Artifact Registry (for Docker Images)
echo "Creating Artifact Registry..."
gcloud artifacts repositories create research-pipeline \
  --repository-format=docker \
  --location=$REGION \
  --description="Docker repository for research pipeline images" || true

# 3. Create the Firestore Database (Firebase)
echo "Initializing Firestore Database..."
gcloud firestore databases create --location=$REGION --type=firestore-native || true

# 4. Create the Cloud Tasks Queue
echo "Creating Cloud Tasks queue..."
gcloud tasks queues create scraper-queue \
  --location=$REGION \
  --max-concurrent-dispatches=100 \
  --max-dispatches-per-second=50 \
  --max-attempts=3 || true

# 5. Create the Cloud Scheduler (Cron Job)
# This triggers the Cloud Workflows orchestrator every Monday at 6 AM.
echo "Creating Cloud Scheduler trigger..."
gcloud scheduler jobs create http weekly-research-run \
  --schedule="0 6 * * 1" \
  --location=$REGION \
  --uri="https://workflowexecutions.googleapis.com/v1/projects/$GCP_PROJECT/locations/$REGION/workflows/research-pipeline-orchestrator/executions" \
  --message-body="{\"argument\": \"{\\\"topic\\\": \\\"Polymarket trading bots\\\"}\"}" \
  --oauth-service-account-email="$(gcloud config get-value account)" || true

echo "========================================"
echo "GCP Setup Complete! ✅"
echo "Your cloud environment is now ready to receive code from GitHub Actions."
echo "========================================"
