# Google Cloud resources (TY6)

Every resource on the trial project. Names only, never values. Region
asia-south1 unless noted.

- Project: `project-cea09bbb-b5f7-4fc4-95b` (number 643396702106), free
  trial credit, expires 26 Jan 2027.
- gcloud runs only from TY6, through the launcher's `CLOUDSDK_CONFIG`.

## APIs enabled

run, artifactregistry, cloudbuild, sqladmin, secretmanager, aiplatform,
iam, iamcredentials, sts, cloudresourcemanager, monitoring, places, routes,
billingbudgets, cloudbilling (all `*.googleapis.com`).

```
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com \
  aiplatform.googleapis.com iamcredentials.googleapis.com iam.googleapis.com \
  sts.googleapis.com cloudresourcemanager.googleapis.com monitoring.googleapis.com \
  places.googleapis.com routes.googleapis.com billingbudgets.googleapis.com
```

## Images and builds

- Artifact Registry: docker repo `ty`
  (`asia-south1-docker.pkg.dev/project-cea09bbb-b5f7-4fc4-95b/ty/<service>:<sha>`).
  Cleanup policy `infra/gcp/ar-cleanup.json`: keep the 10 newest versions,
  delete anything older than 14 days.
- Cloud Build: `infra/cloudbuild/image.yaml` builds one image from the repo
  root. Builds run in asia-south1 as `ty-deploy`, with logs in Cloud
  Logging only.
- Build source bucket: `gs://project-cea09bbb-b5f7-4fc4-95b_cloudbuild`.
  Uniform access, public access prevented, objects deleted after 3 days
  (`infra/gcp/cloudbuild-bucket-lifecycle.json`).

## Service accounts (least privilege)

| Account | Used by | Roles |
| --- | --- | --- |
| `ty-api-run@…` | Cloud Run ty-api | `aiplatform.user`, `cloudsql.client` (project); `secretmanager.secretAccessor` on the four secrets below only |
| `ty-web-run@…` | Cloud Run ty-web | none |
| `ty-deploy@…` | GitHub Actions through WIF; Cloud Build | `run.developer`, `artifactregistry.writer`, `cloudbuild.builds.editor`, `serviceusage.serviceUsageConsumer`, `logging.logWriter`, `logging.viewer` (project); `storage.objectAdmin` on the build bucket only |

No JSON keys exist and none may be created.

Pending (Rohan, see the STOP):
- `iam.serviceAccountUser` for ty-deploy on ty-api-run, ty-web-run and
  itself.
- The WIF `workloadIdentityUser` binding.

## Workload Identity Federation

- Pool `github` (global), OIDC provider `travel-yantra`, issuer
  `https://token.actions.githubusercontent.com`.
- Condition: `assertion.repository=='rohanbalu05/travel-yantra' &&
  assertion.ref=='refs/heads/main'`.
- Provider:
  `projects/643396702106/locations/global/workloadIdentityPools/github/providers/travel-yantra`.
- Repo variables `deploy.yml` reads: `GCP_PROJECT_ID`, `GCP_WIF_PROVIDER`,
  `GCP_DEPLOY_SA`. Until they're set, deploys are deferred.

## Secret Manager (asia-south1 replicas)

`TY_DB_PASSWORD`, `DATABASE_URL`, `GOOGLE_MAPS_API_KEY`, `SERPAPI_API_KEY`:
created without values. `infra/gcp/run-services.sh` mounts a secret only
once it has an enabled version.

## Cloud Run

Set up, and later reconfigured, by `infra/gcp/run-services.sh <service>`.
`deploy.yml` then changes only the image and `GIT_SHA`.

Every service runs with min instances 0, max instances 2, 1 CPU, CPU
throttled, concurrency 40.

| Service | URL | Runtime SA | Memory | Public |
| --- | --- | --- | --- | --- |
| ty-api | https://ty-api-643396702106.asia-south1.run.app | ty-api-run | 1 GiB | not yet (Rohan) |
| ty-web | https://ty-web-643396702106.asia-south1.run.app | ty-web-run | 512 MiB | not yet (Rohan) |

ty-api env:
- `GOOGLE_GENAI_USE_VERTEXAI=true`
- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_CLOUD_LOCATION=global`
- `TY_MODEL_FLASH`, `TY_MODEL_LITE`
- `TY_CORS_ORIGINS` (the ty-web URL)
- `GIT_SHA`

`EMBEDDER` is unset until Rohan picks the embedder (TY2).

ty-web is the Next.js standalone build (`infra/web/Dockerfile`), with
`NEXT_PUBLIC_API_BASE_URL` inlined from ty-api's URL at build time.

Not deployed yet:
- ty-bots, ty-mcp: P2.
- ty-translate: waiting on HQ's IndicTrans2 or Gemini decision.

## Cloud SQL

Not created. It waits for Rohan's yes on the proposal: ty-pg, Postgres 16,
Enterprise, db-f1-micro, 10 GB HDD, zonal.

## Budget

Not created (billing-account access is Rohan's). Proposed: a budget on the
trial's billing account, alerts at 50/90/100% of ₹1,000, or ₹2,500 if
Cloud SQL runs all month.
