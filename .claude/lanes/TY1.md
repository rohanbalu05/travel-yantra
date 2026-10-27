# TY1 core — brief (v3)

Session TY1-core · blue · belt ty-back (MCP: context7) · worktree
`C:\TravelYantra\ty1` · branch `lane/ty1`.

Owns: `packages/contracts/`, `apps/api/core/`, `apps/api/main.py`,
`apps/api/pyproject.toml`, `apps/api/uv.lock`, `apps/api/Dockerfile`,
`apps/api/tests/core/`, `apps/api/tests/conftest.py`.

Objectives served: O1 multi-agent planner (≥90% satisfaction), the API every
channel uses, O3's under-3-second first answer.

Check command (run before every push):
`cd apps/api && uv sync --all-extras && uv run ruff check . && uv run pytest -m "not slow" -q`
and, when you touch contracts, `cd packages/contracts && uv run pytest -q`.

## Packages

- **P0 Turn main green and land the open work (first ~30 min).** Every
  other lane waits on your "MAIN GREEN" message before merging its own.
  Some old PRs may already be merged on GitHub (auto-merge fired when the
  ruleset changed on 27 Oct); check with `gh pr view N --json state`.
  1. For #95 (`ty/ty2-94-ruff-blank-lines`, two blank lines in guide tests)
     and #70 (`ty/ty1-65-guide-deps`, already merged at 19:18 IST): if a PR
     is still open, `git merge --no-ff origin/<branch>`
     (`[TY1] Merge #95 ...`).
  2. Add `[tool.ruff.lint.isort] known-first-party = ["core", "guide",
     "routes", "ty_contracts"]` to `apps/api/pyproject.toml` so import order
     stops drifting between machines; regenerate and commit `uv.lock`.
  3. Run the check command; fix until green (lint and tests, including the
     guide and routes tests that never ran before); `/ty-push`.
  4. Message every lane (TY2-guide, TY3-routes, TY4-web, TY5-channels,
     TY6-infra): `MAIN GREEN <sha> — land your open PR work now`.
  5. Then land #92 (`ty/ty1-79-contracts-dep`) and #80
     (`ty/ty1-02-pipeline-skeleton`, which conflicts with main): merge the
     branch if still open, resolve the pyproject and uv.lock overlap, check,
     push.
  Done when main's CI api job is green on your last push and #95, #70, #92,
  #80 show as merged on GitHub (they close by themselves once their commits
  are on main).
- **P1 Planner end to end on fakes.** Specs: cards #17 (intake), #18
  (solver), #19 (checker and repair loop). Build on #80's ADK skeleton:
  intake → parallel planners → solver → checker and repair → narrator,
  streamed by `POST /plan`. Calls TY3's routes and TY2's guide through their
  routers (mock until they land). Done when the Goa family trip and the
  Mysuru weekend samples each stream their stages and return a valid
  `Itinerary` with fakes in tests, plus one live smoke run on Vertex AI.
- **P2 Revise, save, share, speed.** Cards #20 (revise endpoint), #37
  (trips persistence and share link, Postgres via `DATABASE_URL`), #38
  (first answer under 3 s).

## Interfaces

- Mount `guide.router` (TY2) and `routes.router` (TY3) in `main.py`.
- TY4 consumes the `/plan` stream; agree the event shape with TY4-web early
  and put it in contracts.
- TY5's MCP tools call the API; give TY5-channels the endpoint list.
- TY2 and TY3 ask you for dependencies; add them the same hour.
- TY6 deploys `apps/api` to Cloud Run: keep `apps/api/Dockerfile` building
  from the repo root.

## Notes

- Gemini through Vertex AI: env vars `GOOGLE_GENAI_USE_VERTEXAI`,
  `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, plus model-name env vars.
  Check which location serves the agreed models; record it in the STOP.
- The planner is the hardest part of the project; keep each agent small and
  tested on its own before wiring the chain.
