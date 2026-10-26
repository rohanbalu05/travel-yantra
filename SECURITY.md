# Security policy

## Reporting

This is a student project. Report a vulnerability privately through
GitHub's "Report a vulnerability" (Security tab) on this repository. Please
do not open a public issue for security problems.

## How we handle secrets

- Secrets are stored only in GitHub Actions secrets and Google Secret
  Manager. Code reads them from environment variables.
- No secret values appear in code, fixtures, logs, issues or pull requests.
- Deploys use Workload Identity Federation; there are no service-account
  JSON keys.
- Every pull request is scanned for leaked secrets.

## Data

- This repository holds sample data only. It contains no real phone
  numbers or personal data.
- The live app follows India's DPDP Act: consent before storing personal
  data, and a delete flow for users.
