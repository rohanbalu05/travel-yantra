"""guide.hours: runtime opening hours from Places for corpus places with a place_id. Fakes only."""

import json
from datetime import time
from pathlib import Path

import pytest

from guide import hours as h
from guide.places import MemoryCache, PlacesClient
from guide.planner import place_ids, places_for

FIX = Path(__file__).parent / "fixtures"


class Fake:
    """Places Details with hours; one place id fails."""

    def __init__(self):
        self.calls = []
        self.payload = json.loads((FIX / "places_details.json").read_text())

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append(url)
        if url.endswith("/places/BROKEN"):
            raise TimeoutError("sample timeout")
        return self.payload


@pytest.fixture(autouse=True)
def fresh_budget(monkeypatch):
    monkeypatch.setattr(h, "_spent", {})


def client():
    t = Fake()
    return PlacesClient(cache=MemoryCache(), transport=t, api_key="test-key"), t


def test_only_places_with_a_place_id_get_hours_and_the_cache_serves_repeats():
    goa = places_for("Goa")
    c, t = client()
    out = h.live_hours(goa, c)
    ids = place_ids()
    filled = [p for p in out if p.opening_hours]
    assert {p.id for p in filled} == {p.id for p in goa if p.id in ids} and len(filled) == len(ids) >= 5
    assert filled[0].opening_hours[0].opens == time(10, 0)  # from the fixture, per day
    assert len(t.calls) == len(ids) == c.calls
    h.live_hours(goa, c)  # second trip: all from cache
    assert len(t.calls) == len(ids)


def test_corpus_hours_are_kept_and_nothing_is_fetched_for_karnataka():
    c, t = client()
    mysuru = places_for("Mysuru")
    assert h.live_hours(mysuru, c) == mysuru and t.calls == []


def test_a_failed_lookup_leaves_hours_unknown(monkeypatch):
    goa = places_for("Goa")
    first = next(p for p in goa if p.id in place_ids())
    monkeypatch.setattr(h, "place_ids", lambda: {first.id: "BROKEN"})
    c, _ = client()
    assert h.live_hours(goa, c) == goa


def test_the_daily_cap_bounds_live_calls(monkeypatch):
    monkeypatch.setattr(h, "DAILY_CAP", 2)
    c, t = client()
    h.live_hours(places_for("Goa"), c)
    assert len(t.calls) == 2
    h.live_hours(places_for("Goa"), c)  # budget spent for today
    assert len(t.calls) == 2


def test_without_a_private_cache_or_key_nothing_is_fetched(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    goa = places_for("Goa")
    assert h.live_hours(goa, connect=lambda: pytest.fail("no connection without DATABASE_URL")) == goa
    monkeypatch.setenv("DATABASE_URL", "postgresql://sample")
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    assert h.live_hours(goa, connect=lambda: pytest.fail("no connection without a key")) == goa
