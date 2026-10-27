import json
from pathlib import Path

import pytest

from routes.graph import KIND_PLACE, HaversineRoadProvider, Node
from routes.roads import (
    FIELD_MASK,
    REF,
    URL,
    RoutesApiRoadProvider,
    default_road_provider,
)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "routes_api_blr_goa.json").read_text())
BLR = Node("PL:bengaluru", KIND_PLACE, "Bengaluru", 12.9716, 77.5946)
GOA = Node("PL:panaji", KIND_PLACE, "Panaji", 15.4909, 73.8278)


class FakeTransport:
    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.calls = payload, error, []

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, body, timeout))
        if self.error:
            raise self.error
        return self.payload


def test_uses_routes_api_response_and_sends_essentials_request():
    t = FakeTransport(FIXTURE)
    p = RoutesApiRoadProvider(transport=t, api_key="test-key")
    e = p.road_edge(BLR, GOA)
    assert e.ref == REF and e.mode == "road"
    # recorded live: 591.8 km in 11 h 7 min, Bengaluru to Panaji centres
    assert e.minutes == pytest.approx(40021 / 60)
    assert e.cost_inr == pytest.approx(591.834 * 6.0)
    url, headers, body, _ = t.calls[0]
    assert url == URL and headers["X-Goog-FieldMask"] == FIELD_MASK
    assert body["travelMode"] == "DRIVE" and body["routingPreference"] == "TRAFFIC_UNAWARE"
    assert body == FIXTURE["_request"]  # the fixture answers exactly the request compare sends


def test_caches_so_a_repeat_pair_costs_no_call():
    t = FakeTransport(FIXTURE)
    p = RoutesApiRoadProvider(transport=t, api_key="test-key")
    p.road_edge(BLR, GOA)
    p.road_edge(BLR, GOA)
    assert len(t.calls) == 1 and p.live_calls == 1


def test_no_key_means_no_call_and_haversine(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    t = FakeTransport(FIXTURE)
    e = RoutesApiRoadProvider(transport=t).road_edge(BLR, GOA)
    assert t.calls == [] and e == HaversineRoadProvider().road_edge(BLR, GOA)


def test_cap_stops_live_calls():
    t = FakeTransport(FIXTURE)
    p = RoutesApiRoadProvider(transport=t, api_key="test-key", max_live_calls=1)
    p.road_edge(BLR, GOA)
    e = p.road_edge(GOA, BLR)
    assert len(t.calls) == 1 and e.ref == ""


@pytest.mark.parametrize("payload,error", [(None, OSError("down")), ({"routes": []}, None), ({}, None)])
def test_errors_and_empty_responses_fall_back(payload, error):
    p = RoutesApiRoadProvider(transport=FakeTransport(payload, error), api_key="test-key")
    assert p.road_edge(BLR, GOA) == HaversineRoadProvider().road_edge(BLR, GOA)


def test_default_provider_follows_the_key_and_is_shared(monkeypatch):
    default_road_provider.cache_clear()
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    assert isinstance(default_road_provider(), HaversineRoadProvider)
    default_road_provider.cache_clear()
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")
    shared = default_road_provider()
    assert isinstance(shared, RoutesApiRoadProvider) and default_road_provider() is shared
    default_road_provider.cache_clear()
