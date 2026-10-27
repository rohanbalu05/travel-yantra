# apps/api/core (TY1 core)

FastAPI app, ADK agent pipeline (intake, parallel planners, solver, check-and-repair loop, narrator), revise and trips endpoints.

Run from `apps/api`: `uv sync && TY_FAKE_LLM=1 uv run uvicorn main:app --port 8080`. Test: `uv run pytest tests/core`.

- `GET /health` returns `{"status": "ok", "version": <GIT_SHA or "dev">}`.
- `POST /plan` takes a `TripRequest` (form) or `PlanText` (`{"text", "lang"}`, free text) and streams `PlanEvent`s as Server-Sent Events (`text/event-stream`). Each frame is `data: <PlanEvent JSON>` and a blank line (`by_alias=True`, so `Leg.from_` is `from`); `: ping` comment lines arrive every 15 s while a step runs. Use `fetch` with a stream reader on the web, since `EventSource` cannot POST.
  - Order: `intake`; four `planning` events (`step` transport, places, stays, story; any order); `solving`; then `checking` (with `iteration` and `violations`) and, while something is wrong, `repairing` and `checking` again, at most 3 rounds; an optional last `checking` event when leftovers became `Itinerary.warnings`; `narrating`; `done` with the final Itinerary in `partial` and a `plan_id`.
  - The stream ends after the first `done`, `needs_input` (free text missing origin, destination or dates; up to 3 `questions`) or `error` (`retryable` says whether trying again may help).
- `TY_FAKE_LLM=1` selects `FakeModel` (no model or network calls); tests always force it (`tests/conftest.py`). `core/llm.py` is the only module that reads `GEMINI_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` (use `global`), `TY_MODEL_FLASH` and `TY_MODEL_LITE`. Other lanes call models through `core.llm.get_model()`.
- Modules: `intake.py` (text to TripRequest, Flash-Lite), `solver.py` (days: clustering, nearest neighbour and 2-opt, opening hours, pace), `checker.py` (budget and typed violations), `repair.py` (one repair pass; `check_and_repair` is the plain-Python twin of the LoopAgent), `steps.py` (one function per agent), `pipeline.py` (ADK wiring and the event stream).
- Data: transport comes from TY3's `routes.compare` (sample options when a city is unknown); places and stays are sample-backed (`fakes.py`) until TY2 and TY3 expose planners.
