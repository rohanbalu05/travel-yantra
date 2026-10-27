# TY3 routes — brief (v3)

Session TY3-routes · orange · belt ty-back (MCP: context7) · worktree
`C:\TravelYantra\ty3` · branch `lane/ty3`.

Owns: `apps/api/routes/`, `apps/api/tests/routes/`.

Objectives served: O4 booking links and Dijkstra/A* (60% less planning
time): transport comparison on A* over the multimodal graph, prices across
sellers with booking links, the IRCTC card, the time-on-task measurement.

Check command (run before every push):
`cd apps/api && uv sync --all-extras && uv run ruff check . && uv run pytest -m "not slow" -q`

Dependencies: `apps/api/pyproject.toml` belongs to TY1. Message TY1-core.

## Packages

- **P0 Merge your open work (after TY1's "MAIN GREEN").**
  If #78 is still open (`gh pr view 78 --json state`), `git merge --no-ff origin/ty/ty3-02-dijkstra-astar`; if it already merged, pull (#78). Check, fix,
  push. Until MAIN GREEN arrives, read the routes code and plan P1.
- **P1 Compare transport.** Spec: card #25. `/routes/compare` over the
  graph: rail from the datameet subset, road (Routes API within its free cap,
  with a haversine fallback), air (fake until P2). Ranked options with time,
  cost and changes. Done when Bengaluru → Goa and Bengaluru → Mysuru return
  ranked rail, road and air options, with tests on fixtures.
- **P2 Sellers and prices.** Cards #26 (SerpApi Flights), #27 (SerpApi
  Hotels), #28 (seller registry and deep links). Env var `SERPAPI_API_KEY`
  (if it is not set, build on fixtures and put it under "Needs Rohan").
  SerpApi is on the free plan: cache every response, count every live call,
  at most 20 live calls tonight, record fixtures from them (sanitised).
- **P3 IRCTC and measurement.** Cards #29 (IRCTC copy card and PNR timeline
  mock), #41 (planning-time measurement hooks).

## Interfaces

- Expose `router` in `apps/api/routes/__init__.py`; TY1 mounts it.
- TY1's planner calls compare; TY4's options, itinerary and book pages show
  your results. Agree shapes with TY1-core and TY4-web.
- Rail data build workflow belongs to TY6 (`build-rail.yml`).
