# TY2 guide — brief (v3)

Session TY2-guide · green · belt ty-back (MCP: context7) · worktree
`C:\TravelYantra\ty2` · branch `lane/ty2`.

Owns: `apps/api/guide/`, `apps/api/tests/guide/`, `data/`.

Objectives served: O5 RAG cultural guide (history, food, culture, emergency;
under 3 s) and Katha (2, 5 and 10 minute stories with legend labels).

Check command (run before every push):
`cd apps/api && uv sync --all-extras && uv run ruff check . && uv run pytest -m "not slow" -q`

Dependencies: `apps/api/pyproject.toml` belongs to TY1. Message TY1-core
with the package and version you need.

## Packages

- **P0 Merge your open work (after TY1's "MAIN GREEN").**
  If #77 is still open (`gh pr view 77 --json state`), `git merge --no-ff origin/ty/ty2-02-places-client`; if it already merged, pull (#77, Places API (New)
  client and cache). Check, fix, push. Until MAIN GREEN arrives, read the
  guide code and plan P1; don't push.
- **P1 Guide answers with citations.** Spec: card #23 (`/ask`). Retrieval
  over the ported 112 POIs, 288 chunks and 22 legends (pgvector when
  `DATABASE_URL` is set; tests use fakes). Emergency questions answer from
  Places data, never model memory. Done when five sample questions (history,
  food, culture, an emergency, a legend) return answers with citations, with
  tests on fakes and one live smoke run.
- **P2 Katha.** Spec: card #24, plus `design/katha-style.md`, which is
  binding. Build the pipeline (sourced facts → outline → draft to the word
  budget → self-critique → slop and citation checks), the banned-phrase
  checker as a test, and the taste-gate pack: 3 places × 3 lengths, each with
  a plain-prompt version, saved under `data/katha/taste-gate/`. The taste
  gate is Rohan's; report in the STOP that it is ready.
- **P3 Data and speed.** Cards #21 (Wikimedia fetchers), #22 (Karnataka
  and Goa corridor pipeline), #39 (season scout), #40 (guide under 3 s).

## Interfaces

- Expose `router` in `apps/api/guide/__init__.py`; TY1 mounts it.
- TY1's planner and TY4's Katha and AskGuide pages consume your endpoints;
  agree request and response shapes with TY1-core and TY4-web.
- TY5 translates guide answers and Katha for six languages; keep text and
  citations separable.

## Notes

- Places API (New) within its free cap; cache everything; tests never call it.
- Katha model: the agreed Gemini models only. If quality falls short at the
  taste gate, say so; a bigger model is a cost-gate item.
