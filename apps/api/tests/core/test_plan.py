import asyncio
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from core import pipeline, sse, steps
from core.intake import IntakeDraft
from core.trips import get_store
from main import app
from ty_contracts import Itinerary, PlanEvent, PlanStage

client = TestClient(app)

SAMPLES = pipeline.steps.fakes.SAMPLES
GOA = json.loads((SAMPLES / "goa_family.json").read_text(encoding="utf-8"))["request"]
MYSURU = json.loads((SAMPLES / "mysuru_weekend.json").read_text(encoding="utf-8"))["request"]


def all_frames(resp):
    return [json.loads(line[len("data: "):]) for line in resp.text.splitlines() if line.startswith("data: ")]


def frames(resp):
    """Frames after the instant first event, which every stream starts with (card #38)."""
    events = all_frames(resp)
    assert events[0]["stage"] == "intake" and events[0]["step"] is None and events[0]["partial"] is None
    return events[1:]


def stages(events):
    return [e["stage"] for e in events]


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "dev"}


@pytest.mark.parametrize("body", [GOA, MYSURU], ids=["goa_family", "mysuru_weekend"])
def test_sample_trip_streams_every_stage_and_a_valid_itinerary(body):
    r = client.post("/plan", json=body)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = frames(r)
    for e in events:
        PlanEvent.model_validate(e)
    s = stages(events)
    assert s[0] == "intake" and sorted(s[1:5]) == ["planning"] * 4
    assert sorted(e["step"] for e in events[1:5]) == ["places", "stays", "story", "transport"]
    assert s[5] == "solving" and s[6] == "checking" and s[-2:] == ["narrating", "done"]
    assert events[0]["partial"] is None and events[5]["partial"] is not None
    # The Goa family's flight goes over its budget; round 1 moves every journey to the train (below).
    assert events[6]["iteration"] == 1 and [v["code"] for v in events[6]["violations"]] in ([], ["over_budget"])

    final = Itinerary.model_validate(events[-1]["partial"])
    assert final.request.destinations == body["destinations"]
    assert final.days[0].date == date.fromisoformat(body["start_date"])
    assert len(final.days) == (final.request.end_date - final.request.start_date).days + 1
    assert sum(len(d.stops) for d in final.days) > 0 and final.transport and final.stays
    assert final.budget.within_budget is True
    assert get_store().get(events[-1]["plan_id"]) is not None and events[-1]["share_token"]


def test_goa_family_keeps_relaxed_pace_with_at_most_two_stops_a_day():
    final = Itinerary.model_validate(frames(client.post("/plan", json=GOA))[-1]["partial"])
    assert all(len(d.stops) <= 2 for d in final.days)


def test_free_text_plans_through_intake():
    events = frames(client.post("/plan", json={"text": "Bengaluru se Mysuru, 31 Oct to 1 Nov, do log", "lang": "hi"}))
    assert events[-1]["stage"] == "done"
    final = Itinerary.model_validate(events[-1]["partial"])
    assert final.request.destinations == ["Mysuru"] and final.lang == "hi"


def test_free_text_missing_dates_ends_with_questions():
    events = all_frames(client.post("/plan", json={"text": "Goa trip from Bengaluru with my parents"}))
    assert stages(events) == ["intake", "needs_input"] and events[0]["message"] == "Reading your trip…"
    events = events[1:]
    assert events[0]["questions"] and len(events[0]["questions"]) <= 3
    assert any("date" in q.lower() for q in events[0]["questions"])


def test_over_budget_plan_streams_a_repair_round():
    events = frames(client.post("/plan", json=GOA))
    s = stages(events)
    # The 4-day Goa trip picks the flight (the train is 15 h each way), which takes the family over its
    # ₹60,000 budget: round 1 moves every journey (out and home) to the train and says why.
    first = Itinerary.model_validate(events[5]["partial"])
    assert first.days[0].legs[0].mode.value == "air" and first.transport_reason.startswith("Flight:")
    assert s[6] == "checking" and events[6]["violations"][0]["code"] == "over_budget"
    assert s[7] == "repairing" and events[7]["message"].startswith("Switched to the train to stay within budget")
    final = Itinerary.model_validate(events[-1]["partial"])
    assert final.transport[0].mode.value == "rail" and final.days[0].legs[0].mode.value == "rail"
    assert final.days[-1].legs[-1].role == "home" and final.days[-1].legs[-1].mode.value == "rail"
    assert final.request.transport_mode is None and "over your ₹60,000 budget" in final.transport_reason
    assert final.budget.within_budget is True
    assert final.budget.total_inr < first.budget.total_inr


def test_plan_rejects_bad_request():
    assert client.post("/plan", json={"origin": "x"}).status_code == 422
    assert client.post("/plan", json={"text": ""}).status_code == 422


def test_plan_error_is_single_generic_event(monkeypatch):
    async def boom(state, model):
        raise TimeoutError("model timed out after 20 s")

    monkeypatch.setitem(pipeline.STEPS, "story", boom)
    events = all_frames(client.post("/plan", json=GOA))
    assert events[-1]["stage"] == "error" and events[-1]["retryable"] is True
    assert "timed out" not in json.dumps(events)
    assert stages(events).count("error") == 1


def test_sse_sends_ping_comments_while_waiting():
    async def slow():
        await asyncio.sleep(0.05)
        yield PlanEvent(stage=PlanStage.done, message="Done")

    async def collect():
        return [chunk async for chunk in sse(slow(), ping=0.01)]

    chunks = asyncio.run(collect())
    assert chunks[0] == ": ping\n\n" and chunks[-1].startswith("data: ")
    assert all(c in (": ping\n\n",) or c.startswith("data: ") for c in chunks)


def test_intake_fake_reads_the_goa_message():
    draft = asyncio.run(pipeline.llm.get_model().json("Message:\nBengaluru to Goa 11-14 Dec", IntakeDraft))
    assert draft.destinations == ["Goa"] and draft.start_date == date(2026, 12, 11)


def test_cors_allows_web_origin():
    r = client.options("/plan", headers={"Origin": "https://travel-yantra.web.app", "Access-Control-Request-Method": "POST"})
    assert r.headers["access-control-allow-origin"] == "https://travel-yantra.web.app"


def test_gemini_thinking_level_maps_to_the_genai_config():
    from google.genai import types

    from core.llm import GeminiModel

    m = object.__new__(GeminiModel)  # no client, no network
    m._types = types
    assert m._thinking(None) is None
    assert m._thinking("low").thinking_level == types.ThinkingLevel.LOW
    assert m._thinking("minimal").thinking_level == types.ThinkingLevel.MINIMAL


def test_cors_preflight_allows_localhost_and_env_origins(monkeypatch):
    import importlib

    import main

    pre = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
    r = client.options("/plan", headers={"Origin": "http://localhost:3000", **pre})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "content-type" in r.headers["access-control-allow-headers"].lower()

    monkeypatch.setenv("TY_CORS_ORIGINS", "https://ty-web-abc-el.a.run.app, https://x.example")
    fresh = TestClient(importlib.reload(main).app)
    r = fresh.options("/plan", headers={"Origin": "https://ty-web-abc-el.a.run.app", **pre})
    assert r.headers["access-control-allow-origin"] == "https://ty-web-abc-el.a.run.app"
    assert "access-control-allow-origin" not in fresh.options("/plan", headers={"Origin": "https://evil.example", **pre}).headers
    monkeypatch.delenv("TY_CORS_ORIGINS")
    importlib.reload(main)


def test_first_event_is_instant_and_names_the_trip(monkeypatch):
    async def slow_intake(state, model):
        await asyncio.sleep(5)  # a slow model must not delay the first event
        return {}, "never"

    monkeypatch.setitem(pipeline.STEPS, "intake", slow_intake)

    async def first():
        from ty_contracts import TripRequest

        stream = pipeline.run_plan(TripRequest.model_validate(GOA))
        try:
            return await asyncio.wait_for(anext(stream), timeout=0.5)
        finally:
            await stream.aclose()

    event = asyncio.run(first())
    assert event.stage is PlanStage.intake and event.message == "Planning Bengaluru to Goa…"


def test_mysuru_plan_uses_the_corpus_and_keeps_its_top_sights():
    final = Itinerary.model_validate(frames(client.post("/plan", json=MYSURU))[-1]["partial"])
    stops = [p for d in final.days for p in d.stops]
    assert all(p.source == "travel_yantra_corpus" for p in stops)
    assert {"Mysore Palace", "Chamundeshwari Temple"} <= {p.name for p in stops}
    assert not any(w.startswith("No time left") for w in final.warnings)
