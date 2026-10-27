import datetime as dt
import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from routes import router
from routes.metrics import (
    MemoryStore,
    MetricEvent,
    PgStore,
    RateLimiter,
    StoreFull,
    client_ip,
    get_limiter,
    get_store,
    record,
    summarise,
)

T0 = dt.datetime(2026, 10, 27, 10, 0, tzinfo=dt.UTC)


def ev(session, event, secs, task="plan_goa", arm="ty"):
    return MetricEvent(session_id=session, task=task, arm=arm, event=event, at=T0 + dt.timedelta(seconds=secs))


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_store] = lambda: store
    limiter = RateLimiter()  # fresh per test, so tests never share one budget
    app.dependency_overrides[get_limiter] = lambda: limiter
    return TestClient(app)


def test_summary_medians_per_task_and_arm():
    events = [
        ev("sessaaaa", "start", 0), ev("sessaaaa", "plan_shown", 60), ev("sessaaaa", "booking_chosen", 300),
        ev("sessbbbb", "start", 0), ev("sessbbbb", "plan_shown", 120), ev("sessbbbb", "booking_chosen", 500),
        ev("sesscccc", "start", 0), ev("sesscccc", "plan_shown", 90),
        ev("sessdddd", "start", 0, arm="baseline"), ev("sessdddd", "booking_chosen", 1800, arm="baseline"),
        ev("sesseeee", "plan_shown", 10),  # no start: skipped
    ]
    out = {(s.task, s.arm): s for s in summarise(events)}
    ty, base = out[("plan_goa", "ty")], out[("plan_goa", "baseline")]
    assert (ty.sessions, ty.median_s_to_plan, ty.median_s_to_booking) == (3, 90.0, 400.0)
    assert (base.sessions, base.median_s_to_plan, base.median_s_to_booking) == (1, None, 1800.0)


def test_summary_uses_first_event_and_ignores_events_before_start():
    events = [ev("sessaaaa", "plan_shown", 5), ev("sessaaaa", "start", 10), ev("sessaaaa", "start", 50),
              ev("sessaaaa", "booking_chosen", 70), ev("sessaaaa", "booking_chosen", 40)]
    (s,) = summarise(events)
    assert s.median_s_to_plan is None and s.median_s_to_booking == 30.0


def test_record_stamps_server_time(store):
    e = record(store, MetricEvent(session_id="sessaaaa", task="t", arm="ty", event="start"), now=T0)
    assert e.at == T0 and store.all() == [e]


@pytest.mark.parametrize("bad", [
    {"session_id": "short", "task": "t", "arm": "ty", "event": "start"},
    {"session_id": "9876543210", "task": "t", "arm": "ty", "event": "start"},
    {"session_id": "+919876543210", "task": "t", "arm": "ty", "event": "start"},
    {"session_id": "a@b.example.com", "task": "t", "arm": "ty", "event": "start"},
    {"session_id": "sessaaaa", "task": "t", "arm": "other", "event": "start"},
    {"session_id": "sessaaaa", "task": "t", "arm": "ty", "event": "clicked"},
    {"session_id": "sessaaaa", "task": "t", "arm": "ty", "event": "start", "name": "Arjun"},
])
def test_rejects_personal_or_bad_fields(bad):
    with pytest.raises(ValidationError):
        MetricEvent.model_validate(bad)


def test_http_accepts_json_and_text_plain_beacons(client, store):
    body = {"session_id": "0b9f6c1e-1d2a-4b7e-9a51-3c2d1e0f9a8b", "task": "plan_goa", "arm": "ty"}
    r1 = client.post("/routes/metrics/event", json=dict(body, event="start"))
    r2 = client.post("/routes/metrics/event", content=json.dumps(dict(body, event="booking_chosen")),
                     headers={"content-type": "text/plain;charset=UTF-8"})
    assert (r1.status_code, r2.status_code) == (201, 201) and r1.json() == {"ok": True}
    assert [e.event for e in store.all()] == ["start", "booking_chosen"]
    summary = client.get("/routes/metrics/summary").json()
    assert summary[0]["sessions"] == 1 and summary[0]["median_s_to_booking"] is not None


@pytest.mark.parametrize("content,status", [
    ("not json", 422),
    ('{"session_id": "x"}', 422),
    ('{"session_id": "sessaaaa", "task": "t", "arm": "ty", "event": "start", "pad": "' + "x" * 3000 + '"}', 413),
])
def test_http_rejects_bad_bodies(client, store, content, status):
    r = client.post("/routes/metrics/event", content=content, headers={"content-type": "text/plain"})
    assert r.status_code == status and store.all() == []


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL unset")
def test_pg_store_round_trip():
    s = PgStore(os.environ["DATABASE_URL"])
    e = record(s, MetricEvent(session_id="pgtest-0001", task="pg_round_trip", arm="ty", event="start"))
    assert any(x.session_id == e.session_id and x.task == "pg_round_trip" for x in s.all())


def test_memory_store_is_bounded():
    s = MemoryStore(max_rows=2)
    for secs in range(3):
        s.add(ev("sessaaaa", "start", secs))
    assert [e.at for e in s.all()] == [T0 + dt.timedelta(seconds=1), T0 + dt.timedelta(seconds=2)]


def test_rate_limit_per_ip_over_a_sliding_minute():
    now = [0.0]
    lim = RateLimiter(per_min=3, clock=lambda: now[0])
    assert [lim.allow("1.2.3.4") for _ in range(4)] == [True, True, True, False]
    assert lim.allow("5.6.7.8")  # another IP has its own budget
    now[0] = 60.5
    assert lim.allow("1.2.3.4")


def test_rate_limiter_forgets_old_ips_first():
    lim = RateLimiter(per_min=1, max_keys=2)
    for ip in ("a", "b", "c"):
        assert lim.allow(ip)
    assert list(lim._hits) == ["b", "c"]


@pytest.mark.parametrize("xff,peer,ip", [
    ("6.6.6.6, 203.0.113.9", "10.0.0.1", "203.0.113.9"),  # a forged first entry is ignored
    ("203.0.113.9", None, "203.0.113.9"),
    (None, "10.0.0.1", "10.0.0.1"),
    ("", None, "unknown"),
])
def test_client_ip(xff, peer, ip):
    assert client_ip(xff, peer) == ip


def test_http_rate_limit_returns_429(client, store):
    lim = RateLimiter(per_min=2)
    client.app.dependency_overrides[get_limiter] = lambda: lim
    body = {"session_id": "sessbbbb", "task": "plan_goa", "arm": "ty", "event": "start"}
    codes = [client.post("/routes/metrics/event", json=body, headers={"x-forwarded-for": "203.0.113.9"}).status_code
             for _ in range(3)]
    assert codes == [201, 201, 429] and len(store.all()) == 2
    other = client.post("/routes/metrics/event", json=body, headers={"x-forwarded-for": "203.0.113.10"})
    assert other.status_code == 201


def test_http_full_store_returns_503(client, store):
    def full(e):
        raise StoreFull("metrics store is full")

    store.add = full
    body = {"session_id": "sessbbbb", "task": "plan_goa", "arm": "ty", "event": "start"}
    assert client.post("/routes/metrics/event", json=body).status_code == 503


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL unset")
def test_pg_store_refuses_rows_past_the_cap():
    s = PgStore(os.environ["DATABASE_URL"], max_rows=0)
    with pytest.raises(StoreFull):
        s.add(MetricEvent(session_id="pgtest-0002", task="pg_cap", arm="ty", event="start", at=T0))
