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
# Services deploy private. Public access is a one-time grant by Rohan:
#   gcloud run services add-iam-policy-binding SERVICE --region asia-south1 \
#     --member=allUsers --role=roles/run.invoker
common=(--region "$R" --project "$P" --min-instances 0 --max-instances 2 --cpu 1
        --concurrency 40 --cpu-throttling --quiet)

CONN=$P:$R:ty-pg
VERTEX="GOOGLE_GENAI_USE_VERTEXAI=true@GOOGLE_CLOUD_PROJECT=$P@GOOGLE_CLOUD_LOCATION=global"

url_of() {  # the service's Cloud Run URL, or empty if it doesn't exist yet
  gcloud run services describe "$1" --region "$R" --project "$P" --format 'value(status.url)' 2>/dev/null || true
}

case "${1:-}" in
  ty-api)
    build ty-api apps/api/Dockerfile
    sec=$(secrets_flag DATABASE_URL GOOGLE_MAPS_API_KEY SERPAPI_API_KEY)
    # CORS: both URLs of the web service once it exists (TY1's TY_CORS_ORIGINS).
    # Cloud Run serves a legacy hash URL (status.url) and the project-number URL
    # we hand out; browsers may arrive on either.
    web_url=$(gcloud run services describe ty-web --region "$R" --project "$P" --format 'value(status.url)' 2>/dev/null || true)
    if [ -n "$web_url" ]; then
      num=$(gcloud projects describe "$P" --format 'value(projectNumber)')
      web_url="$web_url,https://ty-web-$num.$R.run.app"
    fi
    # Gemini models are served at the global location on the trial project.
    # ^@^ makes "@" the list separator so the comma-separated CORS value survives.
    # 2 GiB: the image bakes torch and multilingual-e5-small for /guide/ask (V3-T).
    gcloud run deploy ty-api --image "$R-docker.pkg.dev/$P/ty/ty-api:$SHA" "${common[@]}" \
      --service-account "ty-api-run@$P.iam.gserviceaccount.com" --memory 2Gi \
      --add-cloudsql-instances "$CONN" \
      --set-env-vars "^@^$VERTEX@TY_MODEL_FLASH=gemini-3.5-flash@TY_MODEL_LITE=gemini-3.1-flash-lite@EMBEDDER=e5@TY_CORS_ORIGINS=$web_url@GIT_SHA=$SHA" \
      ${sec:+"$sec"}
    ;;
  ty-web)
    build ty-web infra/web/Dockerfile "$(url_of ty-api)"
    gcloud run deploy ty-web --image "$R-docker.pkg.dev/$P/ty/ty-web:$SHA" "${common[@]}" \
      --service-account "ty-web-run@$P.iam.gserviceaccount.com" --memory 512Mi \
      --set-env-vars "GIT_SHA=$SHA"
    ;;
  ty-translate)
    # Private: only ty-bots and ty-mcp call it, with ID tokens (run.invoker below).
    build ty-translate services/translate/Dockerfile
    gcloud run deploy ty-translate --image "$R-docker.pkg.dev/$P/ty/ty-translate:$SHA" "${common[@]}" \
      --service-account "ty-translate-run@$P.iam.gserviceaccount.com" --memory 512Mi \
      --set-env-vars "^@^$VERTEX@TY_MODEL_LITE=gemini-3.1-flash-lite@TY_TRANSLATOR=gemini@GIT_SHA=$SHA"
    for caller in ty-bots-run ty-mcp-run; do
      gcloud run services add-iam-policy-binding ty-translate --region "$R" --project "$P" \
        --member "serviceAccount:$caller@$P.iam.gserviceaccount.com" --role roles/run.invoker --format none
    done
    ;;
  ty-bots)
    # Public for Meta's webhook (the bot verifies Meta's signature itself); the
    # allUsers grant is Rohan's. Phone number id and recipients are secrets too.
    build ty-bots apps/bots/whatsapp/Dockerfile
    sec=$(secrets_flag WHATSAPP_TOKEN WHATSAPP_VERIFY_TOKEN WHATSAPP_APP_SECRET WHATSAPP_PHONE_NUMBER_ID WHATSAPP_ALLOWED_RECIPIENTS)
    gcloud run deploy ty-bots --image "$R-docker.pkg.dev/$P/ty/ty-bots:$SHA" "${common[@]}" \
      --service-account "ty-bots-run@$P.iam.gserviceaccount.com" --memory 512Mi \
      --set-env-vars "^@^API_BASE_URL=$(url_of ty-api)@TRANSLATE_URL=$(url_of ty-translate)@GIT_SHA=$SHA" \
      ${sec:+"$sec"}
    ;;
  ty-mcp)
    build ty-mcp apps/mcp/Dockerfile
    gcloud run deploy ty-mcp --image "$R-docker.pkg.dev/$P/ty/ty-mcp:$SHA" "${common[@]}" \
      --service-account "ty-mcp-run@$P.iam.gserviceaccount.com" --memory 512Mi \
      --set-env-vars "^@^API_BASE_URL=$(url_of ty-api)@TRANSLATE_URL=$(url_of ty-translate)@GIT_SHA=$SHA"
    ;;
  *)
    echo "usage: $0 ty-api|ty-web|ty-translate|ty-bots|ty-mcp" >&2; exit 2 ;;
esac
