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
| `ty-deploy@…` | GitHub Actions through WIF; Cloud Build | `run.developer`, `artifactregistry.writer`, `cloudbuild.builds.editor`, `serviceusage.serviceUsageConsumer`, `logging.logWriter`, `logging.viewer` (project); `storage.objectAdmin` and `storage.legacyBucketReader` on the build bucket only. Builds pass `--gcs-source-staging-dir`, so gcloud skips its default-bucket ownership check, which would need project-wide `storage.buckets.list` |

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
First-time order: ty-api, then ty-web (it inlines the API URL), then ty-api
again so `TY_CORS_ORIGINS` gets the web URL.
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

More services (P2):

| Service | Runtime SA | Memory | Public |
| --- | --- | --- | --- |
| ty-translate | ty-translate-run (aiplatform.user) | 512 MiB | no; run.invoker for ty-bots-run and ty-mcp-run |
| ty-bots | ty-bots-run (reads the WHATSAPP_* secrets) | 512 MiB | yes (allUsers, for Meta's `/webhook`; the bot checks Meta's signature) |
| ty-mcp | ty-mcp-run (no roles) | 512 MiB | no (HQ decision) |

ty-deploy has `iam.serviceAccountUser` on all five runtime SAs (Rohan's
grant). Each new runtime SA needs the same grant before Actions can deploy
it.

### Deploy pipeline notes

- Deploys run on every push to main that touches a service path, through
  WIF. Since 28 Oct 2026, no deploys from the laptop.
- `cancel-in-progress: false`: each run finishes, and only the newest
  waiting run is kept. The plan diffs from the last green deploy.
- Builds use `--async` and poll every 15 s, with matrix `max-parallel: 3`.
  gcloud's own wait polls every second, and five jobs hit Cloud Build's
  per-minute read quota (429).
- Builds pass `--gcs-source-staging-dir`; see the ty-deploy row above.
- After ty-api deploys, one `/guide/ask` warms the e5 model (V3-AC). With
  request-based CPU, the background warm-up thread barely runs.

ty-api now runs with 2 GiB, `EMBEDDER=e5` and the Cloud SQL connector, and
mounts `DATABASE_URL`.

Corpus load: Cloud Run job `ty-load-seed` runs the ty-api image with
`python -m guide.scripts.load_seed`. It runs as ty-api-run with the same
secret and connector, so the DB password never leaves Google Cloud:
`gcloud run jobs update ty-load-seed --image <new ty-api image>` then
`gcloud run jobs execute ty-load-seed --wait`.

## Cloud SQL

Approved by Rohan (V3-V).

- Instance `ty-pg`: Postgres 16, Enterprise, db-f1-micro, 10 GB HDD, no
  auto-increase, zonal, asia-south1. Backups at 20:30 UTC, keeping 7.
- Connection name `project-cea09bbb-b5f7-4fc4-95b:asia-south1:ty-pg`.
- Network: public IP with no authorized networks; TLS required. It's
  reachable only through the Cloud SQL connector or Auth Proxy, with IAM.
- Database `travelyantra`, user `ty` (cloudsqlsuperuser, so the guide
  migration can `create extension vector`).
- The password is in `TY_DB_PASSWORD`, and `DATABASE_URL` is
  `postgresql://ty:…@/travelyantra?host=/cloudsql/<connection name>`. Both
  were generated in the shell and never printed.

## Katha audio (V3-AF)

- API `texttospeech.googleapis.com`, using Chirp 3: HD voices (1M
  characters a month free, then US$30 per 1M).
- Bucket `gs://project-cea09bbb-b5f7-4fc4-95b-katha-audio` in asia-south1,
  uniform access, holding only `katha/<story key>/<lang>/ch<n>.mp3` and one
  `katha/<story key>/<lang>/audio.json` manifest per story (chapter, url,
  voice, characters).
  - `allUsers`: `storage.legacyObjectReader`, so anyone can read an object
    by name but nobody can list the bucket.
  - `ty-api-run`: `objectCreator` and `objectViewer` on this bucket, plus
    `serviceusage.serviceUsageConsumer` on the project for TTS calls.
- ty-api env: `KATHA_AUDIO_BUCKET`, and `KATHA_AUDIO_BASE_URL` =
  `https://storage.googleapis.com/<bucket>`.

## Logging

- Exclusion `ty-bots-verify-token` on the `_Default` sink drops ty-bots
  request lines whose URL carries `hub.verify_token`, because Meta's
  verification GET puts the verify token in the query string. The app logs
  (startup, POST counts, send results) are kept.

## Monitoring

`infra/monitoring/setup.sh`:
- Uptime checks `ty-api-health` (`/health`) and `ty-web-home` (`/`), every
  minute from asia-pacific, europe and usa-oregon, 10 s timeout.
- Dashboard "Travel Yantra latency (O3)" (`latency-dashboard.json`): p95
  per service against 3 s, uptime latency and pass rate, requests by class,
  instances.

## Budget

Not created (billing-account access is Rohan's). Proposed: a budget on the
trial's billing account, alerts at 50/90/100% of ₹1,000, or ₹2,500 if
Cloud SQL runs all month.
