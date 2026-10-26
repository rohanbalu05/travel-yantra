import json
from datetime import date

from fastapi.testclient import TestClient
from ty_contracts import Itinerary, PlanStage

from main import app

client = TestClient(app)

GOA = {"origin": "Bengaluru", "destinations": ["Goa"], "start_date": "2026-12-11", "end_date": "2026-12-14",
       "constraints": {"budget_inr": 60000}}


def frames(resp):
    return [json.loads(line[len("data: "):]) for line in resp.text.splitlines() if line.startswith("data: ")]


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "dev"}


def test_plan_streams_stages_in_order_and_ends_with_itinerary():
    r = client.post("/plan", json=GOA)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = frames(r)
    stages = [e["stage"] for e in events]
    assert stages[0] == "intake"
    assert sorted(stages[1:5]) == ["planning"] * 4
    assert stages[5:] == ["solving", "checking", "narrating", "done"]
    assert events[0]["partial"] is None
    final = Itinerary.model_validate(events[-1]["partial"])
    assert final.request.destinations == ["Goa"]
    assert final.request.start_date == date(2026, 12, 11)
    assert final.days and final.transport and final.stays
    assert final.budget.within_budget is True
    assert PlanStage(events[-1]["stage"]) is PlanStage.done


def test_plan_picks_sample_by_destination():
    events = frames(client.post("/plan", json={**GOA, "destinations": ["Mysuru"]}))
    assert events[-1]["stage"] == "done"
    assert events[-1]["partial"]["request"]["destinations"] == ["Mysuru"]


def test_plan_rejects_bad_request():
    assert client.post("/plan", json={"origin": "x"}).status_code == 422


def test_cors_allows_web_origin():
    r = client.options("/plan", headers={"Origin": "https://travel-yantra.web.app", "Access-Control-Request-Method": "POST"})
    assert r.headers["access-control-allow-origin"] == "https://travel-yantra.web.app"
