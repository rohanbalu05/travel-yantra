#!/usr/bin/env bash
# Builds and deploys a Cloud Run service with its full runtime config.
# Run once per service from the laptop (TY6 only), and again whenever the
# config below changes; deploy.yml afterwards swaps only the image and GIT_SHA.
#   infra/gcp/run-services.sh ty-api
#   infra/gcp/run-services.sh ty-web
# Never prints secret values: secrets are mounted by name from Secret Manager.
set -euo pipefail

P=project-cea09bbb-b5f7-4fc4-95b
R=asia-south1
SHA=$(git rev-parse HEAD)
DEPLOY_SA=ty-deploy@$P.iam.gserviceaccount.com

# Mount NAME=NAME:latest for each secret that has an enabled version.
secrets_flag() {
  local out=()
  for s in "$@"; do
    if [ -n "$(gcloud secrets versions list "$s" --project "$P" --filter=state=enabled --limit 1 --format='value(name)' 2>/dev/null)" ]; then
      out+=("$s=$s:latest")
    else
      echo "  $s has no value yet; not mounted" >&2
    fi
  done
  [ ${#out[@]} -gt 0 ] && echo "--set-secrets=$(IFS=,; echo "${out[*]}")"
  return 0
}

build() {  # name dockerfile [api_url]
  gcloud builds submit . --config infra/cloudbuild/image.yaml --region "$R" \
    --service-account "projects/$P/serviceAccounts/$DEPLOY_SA" \
    --substitutions "_DOCKERFILE=$2,_IMAGE=$R-docker.pkg.dev/$P/ty/$1:$SHA,_API_BASE_URL=${3:-}" \
    --project "$P"
}

# Min instances stay 0 (cost gate); max instances cap a runaway bill.
common=(--region "$R" --project "$P" --min-instances 0 --max-instances 2 --cpu 1
        --concurrency 40 --cpu-throttling --allow-unauthenticated --quiet)

case "${1:-}" in
  ty-api)
    build ty-api apps/api/Dockerfile
    sec=$(secrets_flag DATABASE_URL GOOGLE_MAPS_API_KEY SERPAPI_API_KEY)
    gcloud run deploy ty-api --image "$R-docker.pkg.dev/$P/ty/ty-api:$SHA" "${common[@]}" \
      --service-account "ty-api-run@$P.iam.gserviceaccount.com" --memory 1Gi \
      --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$P,GOOGLE_CLOUD_LOCATION=global,GIT_SHA=$SHA" \
      ${sec:+"$sec"}
    ;;
  ty-web)
    api_url=$(gcloud run services describe ty-api --region "$R" --project "$P" --format 'value(status.url)')
    build ty-web infra/web/Dockerfile "$api_url"
    gcloud run deploy ty-web --image "$R-docker.pkg.dev/$P/ty/ty-web:$SHA" "${common[@]}" \
      --service-account "ty-web-run@$P.iam.gserviceaccount.com" --memory 512Mi \
      --set-env-vars "GIT_SHA=$SHA"
    ;;
  *)
    echo "usage: $0 ty-api|ty-web" >&2; exit 2 ;;
esac
