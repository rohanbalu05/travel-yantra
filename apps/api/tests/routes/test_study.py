import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import router
from routes.metrics import MemoryStore, RateLimiter, get_limiter, get_store
from routes.study import MIN_SESSIONS, TASKS

T0 = dt.datetime(2026, 12, 1, 10, 0, tzinfo=dt.UTC)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    store = MemoryStore()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_limiter] = lambda: RateLimiter(per_min=10_000)
    return TestClient(app)


def run(client, session, task, arm, to_plan_s, to_booking_s, start=T0):
    """One participant through the beacon endpoint, as the web app sends it."""
    for event, secs in (("start", 0), ("plan_shown", to_plan_s), ("booking_chosen", to_booking_s)):
        at = (start + dt.timedelta(seconds=secs)).isoformat()
        r = client.post("/routes/metrics/event", headers={"content-type": "text/plain"},
                        content=f'{{"session_id": "{session}", "task": "{task}", "arm": "{arm}", '
                                f'"event": "{event}", "at": "{at}"}}')
        assert r.status_code == 201


def test_tasks_list_both_arms(client):
    tasks = client.get("/routes/metrics/tasks").json()
    assert [t["id"] for t in tasks] == [t.id for t in TASKS] == ["plan_goa_family", "plan_mysuru_weekend"]
    assert all(set(t["arms"]) == {"ty", "baseline"} and "Bengaluru" in t["brief"] for t in tasks)


def test_report_measures_the_reduction_against_the_60_percent_target(client):
    # counterbalanced: each participant does one task per arm
    for i in range(MIN_SESSIONS):
        run(client, f"base-goa-{i:04d}", "plan_goa_family", "baseline", 900 + i * 60, 1800 + i * 60)
        run(client, f"tyya-goa-{i:04d}", "plan_goa_family", "ty", 120, 540 + i * 30)
        run(client, f"base-mys-{i:04d}", "plan_mysuru_weekend", "baseline", 600, 1200)
        run(client, f"tyya-mys-{i:04d}", "plan_mysuru_weekend", "ty", 90, 600)
    rep = client.get("/routes/metrics/report").json()
    goa, mys = rep["tasks"]
    assert goa["baseline"]["median_s_to_booking"] == 1920 and goa["ty"]["median_s_to_booking"] == 600
    assert goa["reduction_pct"] == 68.8 and goa["met"] is True
    assert mys["reduction_pct"] == 50.0 and mys["met"] is False
    assert rep["overall"]["baseline"]["finished"] == 2 * MIN_SESSIONS and rep["target_pct"] == 60.0
    assert rep["overall"]["reduction_pct"] is not None


def test_no_verdict_before_enough_sessions_or_bookings(client):
    run(client, "base-only-0001", "plan_goa_family", "baseline", 900, 1800)
    run(client, "tyya-only-0001", "plan_goa_family", "ty", 60, 300)
    # a session that never chose a booking counts as started, not finished
    client.post("/routes/metrics/event", json={"session_id": "tyya-left-0001", "task": "plan_goa_family",
                                               "arm": "ty", "event": "start", "at": T0.isoformat()})
    goa = client.get("/routes/metrics/report").json()["tasks"][0]
    assert goa["ty"]["sessions"] == 2 and goa["ty"]["finished"] == 1
    assert goa["reduction_pct"] == pytest.approx(83.3) and goa["met"] is None


def test_report_with_no_events(client):
    rep = client.get("/routes/metrics/report").json()
    assert rep["overall"]["reduction_pct"] is None and all(t["ty"]["sessions"] == 0 for t in rep["tasks"])
