# TY6 infra — brief (v3)

Session TY6-infra · red · belt ty-infra (MCP: context7; CLIs: gcloud,
firebase, gh) · worktree `C:\TravelYantra\ty6` · branch `lane/ty6`.

Owns: `.github/`, `infra/` (except `infra/lanes/`), `fixtures/recorded/`.

Objectives served: O3 availability (live links, uptime check every minute,
p95 under 3 s), O6 cost (budget alert, cost table), deploys for every lane.

Check command (run before every push, for what you touched):
`node --test .github/scripts` and `python -m pytest infra/fixtures -q`
(and `actionlint` if it is installed).

## Google Cloud

- Only project `project-cea09bbb-b5f7-4fc4-95b`, the free trial of Rohan's
  secondary account (₹28,796.63 credit, expires 26 Jan 2027). The launcher
  sets `CLOUDSDK_CONFIG`; never log in, switch accounts, or touch another
  project. Never upgrade the trial.
- The deny list in your settings sends these to Rohan first: deleting
  projects, Cloud SQL instances, buckets, services or repositories; billing
  account changes; service-account key files; auth and account changes. Ask
  in your STOP under "Needs Rohan".
- Region asia-south1 unless a service isn't offered there (say so).

## Packages

- **P0 Merge your open work and tidy CI (after TY1's "MAIN GREEN").**
  For #96 (`ty/ty6-94-web-ci`, with TY4's #93) and #91
  (`ty/ty6-07-root-context-build`): if still open (`gh pr view N --json
  state`), `git merge --no-ff origin/<branch>`; if already merged, pull.
  Then:
  - CI stays on push to main; it's informational (no PRs anymore).
  - Retire the PR-only machinery: `review-gate.yml`, `backup-review.yml`
    (and leave `guard.yml` and `strip-attribution.yml` harmless or remove
    them; say which).
  - Deploys run on push to main with path filters (api, web, mcp, bots,
    translate) and a concurrency group that cancels older runs.
- **P1 Google Cloud foundation and hosting.** Cards #14 and #15:
  - enable the APIs (Cloud Run, Artifact Registry, Cloud Build, Cloud SQL
    Admin, Secret Manager, Vertex AI, IAM Credentials, Monitoring, Places
    API (New), Routes);
  - an Artifact Registry repository;
  - runtime and deploy service accounts with least privilege;
  - Workload Identity Federation for `rohanbalu05/travel-yantra` (no JSON
    keys);
  - Cloud SQL Postgres 16 on the smallest shared-core tier with pgvector,
    its password in Secret Manager;
  - Cloud Run services for the API and the web app (minimum instances 0);
  - a budget alert at ₹1,000 on the trial's billing account.

  Done when the live API and web URLs answer, recorded in the STOP.
- **P2 Fixtures, uptime, latency.** Cards #16 (record real API fixtures,
  sanitised), #46 (uptime check every minute and a latency dashboard), plus
  the bot, MCP and translate services on Cloud Run for TY5.

## Notes

- GitHub repo settings that the lanes' token can't change go under "Needs
  Rohan" with exact clicks.
- Secrets: Secret Manager for runtime; GitHub Actions secrets and variables
  by name; never print values.
- Report main's CI state in every STOP.
