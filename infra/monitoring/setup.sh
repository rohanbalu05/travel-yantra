#!/usr/bin/env bash
# Uptime checks (every minute, 3 regions) and the latency dashboard (O3).
# Run once from the laptop (TY6 only). Free: about 260k check runs a month
# against Cloud Monitoring's 1M free; dashboards cost nothing.
# Git Bash on Windows rewrites "/health" into a Windows path; the exclusion
# below keeps --path= arguments as written.
set -euo pipefail
export MSYS2_ARG_CONV_EXCL="--path="

P=project-cea09bbb-b5f7-4fc4-95b
NUM=$(gcloud projects describe "$P" --format 'value(projectNumber)')

check() {  # name host path
  gcloud monitoring uptime create "$1" --project "$P" --resource-type=uptime-url \
    --resource-labels="host=$2,project_id=$P" --protocol=https --path="$3" \
    --period=1 --timeout=10 --regions=asia-pacific,europe,usa-oregon --status-codes=200
}

check ty-api-health "ty-api-$NUM.asia-south1.run.app" /health
check ty-web-home "ty-web-$NUM.asia-south1.run.app" /
gcloud monitoring dashboards create --project "$P" \
  --config-from-file="$(dirname "$0")/latency-dashboard.json"
