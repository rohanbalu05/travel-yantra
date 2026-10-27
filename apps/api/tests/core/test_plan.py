import asyncio
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from core import pipeline, sse, steps
from core.intake import IntakeDraft
from main import app
from ty_contracts import Itinerary, PlanEvent, PlanStage

client = TestClient(app)

SAMPLES = pipeline.steps.fakes.SAMPLES
GOA = json.loads((SAMPLES / "goa_family.json").read_text(encoding="utf-8"))["request"]
MYSURU = json.loads((SAMPLES / "mysuru_weekend.json").read_text(encoding="utf-8"))["request"]


def frames(resp):
    return [json.loads(line[len("data: "):]) for line in resp.text.splitlines() if line.startswith("data: ")]


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
    assert events[6]["iteration"] == 1 and events[6]["violations"] == []

    final = Itinerary.model_validate(events[-1]["partial"])
    assert final.request.destinations == body["destinations"]
    assert final.days[0].date == date.fromisoformat(body["start_date"])
    assert len(final.days) == (final.request.end_date - final.request.start_date).days + 1
    assert sum(len(d.stops) for d in final.days) > 0 and final.transport and final.stays
    assert final.budget.within_budget is True
    assert events[-1]["plan_id"] in pipeline.PLANS


def test_goa_family_keeps_relaxed_pace_with_at_most_two_stops_a_day():
    final = Itinerary.model_validate(frames(client.post("/plan", json=GOA))[-1]["partial"])
    assert all(len(d.stops) <= 2 for d in final.days)


def test_free_text_plans_through_intake():
    events = frames(client.post("/plan", json={"text": "Bengaluru se Mysuru, 31 Oct to 1 Nov, do log", "lang": "hi"}))
    assert events[-1]["stage"] == "done"
    final = Itinerary.model_validate(events[-1]["partial"])
    assert final.request.destinations == ["Mysuru"] and final.lang == "hi"


def test_free_text_missing_dates_ends_with_questions():
    events = frames(client.post("/plan", json={"text": "Goa trip from Bengaluru with my parents"}))
    assert stages(events) == ["needs_input"]
    assert events[0]["questions"] and len(events[0]["questions"]) <= 3
    assert any("date" in q.lower() for q in events[0]["questions"])


def test_over_budget_plan_streams_a_repair_round(monkeypatch):
    cheap_first = steps.fakes.transport

    def air_first(request):
        return list(reversed(cheap_first(request)))

    monkeypatch.setattr(steps, "transport_options", air_first)
    events = frames(client.post("/plan", json=GOA))
    s = stages(events)
    assert s[6:9] == ["checking", "repairing", "checking"]
    assert events[6]["violations"][0]["code"] == "over_budget"
    assert events[7]["iteration"] == 1 and events[8]["iteration"] == 2 and events[8]["violations"] == []
    final = Itinerary.model_validate(events[-1]["partial"])
    assert final.transport[0].mode.value == "rail" and final.budget.within_budget is True


def test_plan_rejects_bad_request():
    assert client.post("/plan", json={"origin": "x"}).status_code == 422
    assert client.post("/plan", json={"text": ""}).status_code == 422


def test_plan_error_is_single_generic_event(monkeypatch):
    async def boom(state, model):
        raise TimeoutError("model timed out after 20 s")

    monkeypatch.setitem(pipeline.STEPS, "story", boom)
    events = frames(client.post("/plan", json=GOA))
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
