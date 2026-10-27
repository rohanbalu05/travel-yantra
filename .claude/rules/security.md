# Security and data (v3)

## Secrets

- Secrets live only in Rohan's Windows user environment variables, GitHub
  Actions secrets and Google Secret Manager. Code reads them from env vars.
  Use and mention env var names only (for example `SERPAPI_API_KEY`).
- Never print, log, echo, commit or paste a secret value. Never ask anyone
  to paste one. Never run commands that dump the environment (`env`,
  `printenv`, `set`, `Get-ChildItem env:`).
- Do not add `.env` files; `.env.example` with names only is fine.
- No service-account key files (JSON keys). Local code uses Application
  Default Credentials from the trial account; Cloud Run uses its service
  account; GitHub Actions deploys with Workload Identity Federation.
- The pre-commit hook blocks common key and token patterns and secret files.
  If it blocks you, remove the secret; never bypass the hook.

## Accounts and isolation

- Google Cloud: only the secondary account's trial project
  `project-cea09bbb-b5f7-4fc4-95b`, through the gcloud config folder the
  launcher sets (`CLOUDSDK_CONFIG`). Never log in, switch accounts or point
  gcloud at any other project. Only TY6 runs gcloud or firebase.
- GitHub: lanes use a token scoped to `rohanbalu05/travel-yantra` only
  (`GH_TOKEN`, set by the launcher). Never clone, read into or write to any
  other repository.
- Easilydone (another organisation and account) is off limits for every
  lane, always.

## Data

- Never capture card numbers, UPI IDs, OTPs or passwords.
- Public repo: sample data only. Use the sample persona (Arjun Rao and
  family) and sample PNRs and fares. No real phone numbers or personal data.
- Recorded fixtures must be sanitised (no keys, tokens, phone numbers or
  personal data).
- WhatsApp messages go only to the test recipients Rohan adds. No WhatsApp
  Business account settings from a lane.

## Live calls

- Tests never call live APIs or models.
- Small live smoke calls are allowed (see `loop.md`), through the trial
  project or the agreed free APIs, cached, and listed in the STOP.

## Destructive operations

Dropping tables or databases, deleting buckets, services, projects or
repositories, force-pushing, rewriting main: never by a lane. Put them under
"Needs Rohan".
