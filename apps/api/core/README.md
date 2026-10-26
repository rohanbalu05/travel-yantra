# apps/api/core (TY1 core)

FastAPI app, ADK agent pipeline (intake, parallel planner, solver, checker and repair, narrator), revise and trips endpoints.

Run from `apps/api`: `uv sync && TY_FAKE_LLM=1 uv run uvicorn main:app --port 8080`. Test: `uv run pytest tests/core`.

- `GET /health` returns `{"status": "ok", "version": <GIT_SHA or "dev">}`.
- `POST /plan` takes a `TripRequest` and streams `PlanEvent`s as Server-Sent Events (`text/event-stream`). Each frame is `data: <PlanEvent JSON>` followed by a blank line; the JSON is `PlanEvent.model_dump_json(by_alias=True)` (so `Leg.from_` is `from`). Stage order: `intake`, four `planning` events (transport, places, stays, story, in any order), `solving`, `checking`, `narrating`, `done`. `partial` is null until the solver has built the Itinerary; `done` always carries the final Itinerary. On failure the stream ends with a single `error` event. Use `fetch` with a stream reader on the web, since `EventSource` cannot POST.
- `TY_FAKE_LLM=1` selects fake agents that read `packages/contracts/samples` (no model or network calls). `core/llm.py` is the only module that reads `GEMINI_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `TY_MODEL_FLASH` and `TY_MODEL_LITE`.
