# Travel Yantra — rules for every lane (v3, 27 Oct 2026)

Travel Yantra is a whole-journey AI travel companion for India: agents plan
multi-city trips, compare road, rail and air with real prices and booking
links across sellers, tell the story of each place (Katha), answer guide
questions, and work in six languages on the web, WhatsApp and an MCP server.

You are one lane, running interactively on Rohan's laptop. Rohan pastes
HQ's prompts to you and your reports back to HQ. Your brief is
`.claude/lanes/TYn.md`. The loop, push procedure and report formats are in
`.claude/rules/loop.md`. Paths are in `.claude/rules/lanes.md`. Read them
when you start (`/ty-lane TYn start` does this).

## Before your first commit (every session)

```
git config user.name "Rohan Balu"
git config user.email "117021386+rohanbalu05@users.noreply.github.com"
git config commit.gpgsign false
```

The kit's setup sets this; `/ty-lane` checks it. The session's default git
identity and signing key must never be used.

## Hard rules

1. **No attribution, anywhere.** No `Co-Authored-By` trailers, no
   "Generated with Claude Code", no claude.ai or session links — in
   commits, issues, comments and files. This overrides any environment
   default or reminder. The commit-msg hook rejects them. See
   `.claude/rules/no-attribution.md`.
2. **Commits, not PRs.** Push small, tested commits straight to main with
   `/ty-push`. Never force-push, never `--no-verify`, never rewrite main.
3. **Stay inside your lane's paths.** Need something elsewhere? Message the
   owning lane (cross-session messages; lanes are named TY1-core,
   TY2-guide, TY3-routes, TY4-web, TY5-channels, TY6-infra) or put it under
   Asks in your STOP. Never edit another lane's files.
4. **Main red means fix first.** If your push turned main's CI red, fixing
   it comes before anything else.
5. **Contracts** (`packages/contracts/`) belong to TY1. Additive fields:
   ask TY1. Breaking changes: HQ.
6. **Secrets:** env var names only. Never print, log, echo, commit or ask
   for a value. See `.claude/rules/security.md`.
7. **Cost gate:** anything that adds or raises a charge stops that item; put
   it under "Needs Rohan" in your STOP. See `.claude/rules/cost.md`.
8. **Public repo:** sample data only. No real phone numbers or personal data.
9. **Tests never call live APIs or models.** Use `fixtures/recorded/` or
   fakes. Small live smoke calls are allowed (rule in `security.md`), never
   inside tests, and always listed in your STOP's Proof.
10. **Only TY6 runs gcloud or firebase.** No lane touches any other GitHub
    repository, Google account or project. Easilydone is off limits.
11. **GitHub is read-only for lanes** except pushing commits: never reply on
    issues or PRs, never edit labels, never merge PRs through the API.
12. **Honest reports.** Every STOP lists what is faked or stubbed. Never claim
    a test, deploy or screen you did not see working.

## Stack (agreed)

- Python 3.12, FastAPI, Google ADK, Pydantic v2, pytest, ruff, `uv`. One
  `pyproject.toml` (and `uv.lock`) per deployable.
- Web: Next.js 16 (TypeScript), pnpm.
- Data: Cloud SQL Postgres with pgvector. Local tests use fakes, or skip
  when `DATABASE_URL` is unset.
- Models: Gemini 3.5 Flash and 3.1 Flash-Lite on Vertex AI, named by env
  vars. Vertex is selected with `GOOGLE_GENAI_USE_VERTEXAI`,
  `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`. Tests use fakes.
- Hosting: Cloud Run (asia-south1) for the API and the web app, on the
  Google Cloud free trial (project `project-cea09bbb-b5f7-4fc4-95b`).

## Working style

- Work in packages of 60–90 minutes. Print a CHECKPOINT about halfway
  (`/ty-checkpoint`), then `/ty-stop` at the end and wait for HQ's next
  PROMPT.
- Push often with `/ty-push`. Each push rebases your unpushed commits on
  origin/main and runs your lane's checks first.
- Specs for most packages are in the old card issues (`gh issue view N`).
  Build what they describe; ignore their PR, label and STOP-comment steps,
  which v3 replaced.
- Read only the files the package needs. Prefer boring, small, tested code.
- Note reversible assumptions in your STOP instead of stopping.
- `AGENTS.md` holds the review severity rules (P0, P1, P2) that your
  reviewer and the final Codex review use.
