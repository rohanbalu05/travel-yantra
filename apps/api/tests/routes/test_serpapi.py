import datetime as dt

from routes import apicache
from routes.apicache import FileStore, MemoryStore
from routes.serpapi import SerpApi, sanitise

PARAMS = {"engine": "google_hotels", "q": "hotels in Coorg", "check_in_date": "2026-12-11",
          "check_out_date": "2026-12-14", "adults": "2"}


class Counting:
    def __init__(self, payload=None, error=None):
        self.payload = payload if payload is not None else {"properties": []}
        self.error = error
        self.calls = 0

    def __call__(self, url, timeout):
        self.calls += 1
        if self.error:
            raise self.error
        return self.payload


def test_fixture_answer_is_cached(serp):
    api, t = serp
    first = api.get(PARAMS, 60)
    assert first["properties"] and api.get(PARAMS, 60) == first
    assert len(t.calls) == 1 and api.live_calls == 1


def test_no_key_makes_no_call():
    t = Counting()
    assert SerpApi(store=MemoryStore(), transport=t).get(PARAMS, 60) is None
    assert t.calls == 0


def test_daily_cap_is_shared_and_stops_live_calls():
    store, t = MemoryStore(), Counting()
    a = SerpApi(store=store, transport=t, api_key="k", daily_cap=1)
    b = SerpApi(store=store, transport=t, api_key="k", daily_cap=1)  # a second instance, same store
    assert a.get(PARAMS, 60) is not None
    assert b.get({**PARAMS, "q": "hotels in Hampi"}, 60) is None
    assert t.calls == 1
    # a refused daily spend leaves the monthly count alone
    assert store.count("serpapi", apicache.month_period()) == 1


def test_monthly_cap():
    t = Counting()
    api = SerpApi(store=MemoryStore(), transport=t, api_key="k", monthly_cap=0)
    assert api.get(PARAMS, 60) is None and t.calls == 0


def test_stale_answer_served_when_capped():
    store, t = MemoryStore(), Counting()
    SerpApi(store=store, transport=t, api_key="k").get(PARAMS, ttl_s=-1)  # stored already expired
    capped = SerpApi(store=store, transport=t, api_key="k", daily_cap=1)
    assert capped.get(PARAMS, 60) == {"properties": []}
    assert t.calls == 1


def test_errors_are_not_cached_as_answers_and_not_retried_at_once():
    for err in (Counting(error=TimeoutError()), Counting(payload={"error": "Invalid key"})):
        store = MemoryStore()
        api = SerpApi(store=store, transport=err, api_key="k")
        assert api.get(PARAMS, 60) is None and api.get(PARAMS, 60) is None
        assert err.calls == 1
        store._cache.pop(next(k for k in store._cache if k.endswith(":error")))  # the 10 minutes pass
        ok = Counting()
        assert SerpApi(store=store, transport=ok, api_key="k").get(PARAMS, 60) == {"properties": []}
        assert ok.calls == 1


def test_sanitise_drops_metadata_phones_and_key():
    raw = {"search_metadata": {"id": "x"}, "properties": [{"name": "A", "phone": "+91 00000 00000",
                                                           "link": "https://x/?api_key=sekret"}]}
    clean = sanitise(raw, "sekret")
    assert clean == {"properties": [{"name": "A", "link": ""}]}


def test_live_answers_are_sanitised_before_caching():
    store = MemoryStore()
    t = Counting(payload={"search_metadata": {"json_endpoint": "x"}, "properties": [{"name": "A", "phone": "1"}]})
    assert SerpApi(store=store, transport=t, api_key="k").get(PARAMS, 60) == {"properties": [{"name": "A"}]}


def test_file_store_is_shared_between_instances(tmp_path):
    path = tmp_path / "c.json"
    a, b = FileStore(path), FileStore(path)
    assert a.spend("serpapi", "2026-10-27", 2) and b.spend("serpapi", "2026-10-27", 2)
    assert not a.spend("serpapi", "2026-10-27", 2)
    a.set("k", {"v": 1}, 60)
    assert FileStore(path).get("k") == {"v": 1}
    assert FileStore(path).count("serpapi", "2026-10-27") == 2


def test_periods_use_india_time():
    late = dt.datetime(2026, 10, 27, 19, 0, tzinfo=dt.UTC)  # 00:30 IST on the 28th
    assert apicache.day_period(late) == "2026-10-28" and apicache.month_period(late) == "2026-10"


def test_usage_counts_live_calls_against_the_caps(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routes import apicache, router
    from routes.serpapi import PROVIDER

    monkeypatch.setenv("SERPAPI_MONTHLY_CAP", "90")
    store = apicache.get_store()
    assert store.spend(PROVIDER, apicache.month_period(), 90) and store.spend(PROVIDER, apicache.day_period(), 20)
    app = FastAPI()
    app.include_router(router)
    body = TestClient(app).get("/routes/usage").json()
    assert body["serpapi"] == {"month": 1, "month_cap": 90, "today": 1, "day_cap": 20, "plan_left": None}
    assert body["routes_api"]["month"] == 0 and body["routes_api"]["month_cap"] > 0
    assert "key" not in str(body).lower()


def test_live_calls_stop_ten_short_of_the_plans_remainder():
    """The Account API (free) says how many searches the plan has left; live calls stop RESERVE short."""
    from routes.apicache import MemoryStore
    from routes.serpapi import SerpApi

    left = {"n": 12}
    calls = []

    def transport(url, timeout):
        calls.append(url.split("?")[0])
        if "account.json" in url:
            return {"total_searches_left": left["n"], "api_key": "secret", "account_email": "x@example.com"}
        return {"ok": len(calls)}

    store = MemoryStore()
    api = SerpApi(store=store, transport=transport, api_key="k", daily_cap=100, monthly_cap=100, account=True)
    assert api.get({"q": "a"}, 60) is not None and api.get({"q": "b"}, 60) is not None
    assert api.get({"q": "c"}, 60) is None  # 12 left, 2 spent since the check: 10, the reserve
    assert calls.count("https://serpapi.com/account.json") == 1  # cached between calls
    assert "secret" not in str(store.get("serpapi:account")) and "example" not in str(store.get("serpapi:account"))


def test_unknown_remainder_falls_back_to_the_caps():
    from routes.apicache import MemoryStore
    from routes.serpapi import SerpApi

    def transport(url, timeout):
        if "account.json" in url:
            raise TimeoutError
        return {"ok": True}

    api = SerpApi(store=MemoryStore(), transport=transport, api_key="k", daily_cap=1, monthly_cap=5, account=True)
    assert api.get({"q": "a"}, 60) is not None and api.get({"q": "b"}, 60) is None  # the daily cap
