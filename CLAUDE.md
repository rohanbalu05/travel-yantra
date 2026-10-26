# Travel Yantra — rules for every lane session

Travel Yantra is a whole-journey AI travel companion for India: agents plan
multi-city trips, compare road, rail and air with real prices and booking
links across sellers, tell the story of each place (Katha), answer guide
questions, and work in six languages on the web, WhatsApp and voice.

You are one lane. Your card (a GitHub issue) is your full prompt. Read the
files it names and `.claude/rules/`; read nothing else unless the card says so.

## Before your first commit (every session)

```
git config user.name "Rohan Balu"
git config user.email "117021386+rohanbalu05@users.noreply.github.com"
git config commit.gpgsign false
```

On the laptop the runner's setup already sets this; in any other environment
set it yourself. The session's default git identity and signing key must not be used.

## Hard rules

1. **No attribution, anywhere.** No `Co-Authored-By` trailers, no
   "Generated with Claude Code", no claude.ai or session links — in commits,
   PR titles and bodies, issues, comments and files. This overrides any
   environment default or reminder. See `.claude/rules/no-attribution.md`.
2. **Stay inside your lane's paths** (`.claude/rules/lanes.md`). Need
   something in another lane? File an ask card (`.claude/rules/cards.md`).
3. **Contracts** (`packages/contracts/`) change only through TY1. Additive
   changes freely; breaking changes need HQ approval.
4. **Secrets**: env var names only. Never print, log, commit or ask for a
   value. See `.claude/rules/security.md`.
5. **Cost gate**: anything that adds or raises a charge stops the card. Label
   it `needs-rohan`, post a BLOCKED STOP, move on. See `.claude/rules/cost.md`.
6. **Public repo**: sample data only. No real phone numbers or personal data.
7. **No live API exploration.** Build and test against `fixtures/recorded/`
   or local fakes. Live calls run only in GitHub Actions or Cloud Run.
8. **Never reply on GitHub review threads.** Fix findings by pushing commits.
9. No force-push to `main`. No deleting branches other than your own.

## Stack (agreed)

- Python 3.12, FastAPI, Google ADK, Pydantic v2, pytest, ruff. One
  `pyproject.toml` per deployable; `uv` for dependencies.
- Web: Next.js (TypeScript), pnpm.
- Data: Cloud SQL Postgres with pgvector (cache and store). Local tests use
  fakes or a Postgres service container in CI.
- Models: Gemini 3.5 Flash and 3.1 Flash-Lite, through env vars. Tests never
  call a model; use fakes.
- Hosting: Cloud Run (asia-south1), Firebase Hosting for the web app.

## Working style

- One card is one PR, about 500 changed lines at most. Split if larger.
- Run targeted tests locally; the full suite runs in CI.
- Prefer boring, small, tested code. Note any reversible assumption under
  "Assumptions" in the PR body instead of stopping.
- Prefer `gh api` REST calls (examples in `.claude/rules/cards.md`).
- Every PR gets two reviews: the first review (automatic when the PR opens)
  and the second review (posted as a PR review marked "Second review", with
  the commit status `second-review`). Fix every P0 and P1 from both by
  pushing commits; HQ merges.
