#!/usr/bin/env bash
# Uptime checks (every minute, 3 regions) and the latency dashboard (O3).
# Run once from the laptop (TY6 only); a re-run makes a second dashboard, so
# re-run only the check lines you need. Free: each check runs from 3 regions, so
# a 1-minute check is about 130k runs a month and a 5-minute one about 26k; the
# four below are about 415k against Cloud Monitoring's 1M free. Dashboards are free.
# Git Bash on Windows rewrites "/health" into a Windows path; the exclusion
# below keeps --path= arguments as written.
set -euo pipefail
export MSYS2_ARG_CONV_EXCL="--path="

P=project-cea09bbb-b5f7-4fc4-95b
NUM=$(gcloud projects describe "$P" --format 'value(projectNumber)')

check() {  # name host path [period_minutes, default 1]
  gcloud monitoring uptime create "$1" --project "$P" --resource-type=uptime-url \
    --resource-labels="host=$2,project_id=$P" --protocol=https --path="$3" \
    --period="${4:-1}" --timeout=10 --regions=asia-pacific,europe,usa-oregon --status-codes=200
}

check ty-api-health "ty-api-$NUM.asia-south1.run.app" /health
check ty-web-home "ty-web-$NUM.asia-south1.run.app" /
# P6: trip mode, and TY2's nearby search near Old Goa. Nearby runs every 5 minutes:
# each run can reach Google Places (TY2 caches 24 h), so it stays well inside the
# free cap.
check ty-web-trip-live "ty-web-$NUM.asia-south1.run.app" /trip/live/
check ty-api-nearby "ty-api-$NUM.asia-south1.run.app" "/guide/nearby?lat=15.5009&lng=73.9116&kind=hospital&limit=1" 5
gcloud monitoring dashboards create --project "$P" \
  --config-from-file="$(dirname "$0")/latency-dashboard.json"
