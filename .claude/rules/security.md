# Security and data

- Secrets live only in GitHub Actions secrets, Google Secret Manager or
  cloud-environment credentials. Code reads them from env vars. Use and
  mention env var names only (for example `GEMINI_API_KEY`).
- Never print, log, echo, commit or paste a secret value. Never ask anyone
  to paste one. Do not add `.env` files; `.env.example` with names only is fine.
- Never capture card numbers, UPI IDs, OTPs or passwords.
- Public repo: sample data only. Use the sample persona (Arjun Rao and
  family) and sample PNRs and fares. No real phone numbers or personal data.
- Recorded fixtures must be sanitised (no keys, tokens, phone numbers or
  personal data).
- Never use the "Labs → Language Applications → AIDA" billing account or the
  project `automatic-space-pj5r3`.
- WhatsApp messages go only to the test recipients Rohan adds. No WhatsApp
  Business account actions from a lane.
- Destructive operations (dropping tables or databases, deleting buckets,
  projects or repos, force-pushing to main) are never done by a lane.
