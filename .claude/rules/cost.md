# Cost gate (v3)

Stop the item before building, enabling or recommending anything that adds
or raises a charge: a cloud service or setting outside the agreed list, a
bigger tier, a model or tier change, a new vendor or paid API plan, a paid
call pattern outside the agreed free caps, a domain, SMS, or a free tier we
would outgrow.

When that happens:

1. Do not build the paid part; build the rest.
2. Put it under "Needs Rohan" in your STOP: what changes; the cost in ₹ with
   the price source and date; any one-time cost; which account pays; the
   cheaper option.

## Agreed (no stop needed)

- The Google Cloud free trial credit on project
  `project-cea09bbb-b5f7-4fc4-95b` (₹28,796.63, expires 26 Jan 2027): Cloud
  Run, Cloud SQL Postgres on the smallest shared-core tier, Artifact
  Registry, Cloud Build, Secret Manager, Cloud Monitoring uptime checks,
  Vertex AI Gemini 3.5 Flash and 3.1 Flash-Lite, Places and Routes within
  their free caps.
- Firebase Hosting (free tier), GitHub Actions (public repo), the WhatsApp
  test number, Wikimedia, datameet, the SerpApi free plan (count every call;
  cache everything), the AI Studio free tier.

## Always a stop

- Clicking or scripting anything that upgrades the trial to a paid account.
- Gemini Pro or any model outside the two agreed ones.
- GPUs, bigger Cloud SQL tiers, minimum instances above 0 on Cloud Run.
- Any paid plan, credit purchase, domain or SMS.
- The "Labs → Language Applications → AIDA" billing account or the project
  `automatic-space-pj5r3`: never, for anything.

Code that calls a paid or capped API must cache responses and must not run
in tests.
