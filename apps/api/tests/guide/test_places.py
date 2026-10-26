import json
from pathlib import Path

import pytest
from guide.places import DETAILS_MASK, HOURS_MASK, LIST_MASK, MemoryCache, PlacesClient

FIX = Path(__file__).parent / "fixtures"


class FakeTransport:
    def __init__(self, fixture: str):
        self.payload = json.loads((FIX / fixture).read_text())
        self.calls: list[tuple] = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body, timeout))
        return self.payload


def client(fixture, cache=None):
    t = FakeTransport(fixture)
    return PlacesClient(cache=cache, transport=t, api_key="test-key"), t


def test_places_search_converts_and_masks():
    c, t = client("places_search.json")
    places = c.search("Mysuru palace")
    assert [p.name for p in places] == ["Mysore Palace", "Chamundeshwari Temple"]
    assert places[1].category == "hindu_temple" and places[0].source == "google_places"
    _, url, headers, body, timeout = t.calls[0]
    assert url.endswith("/places:searchText")
    assert headers["X-Goog-FieldMask"] == LIST_MASK
    assert body["textQuery"] == "Mysuru palace" and timeout > 0


def test_places_second_lookup_hits_cache():
    c, t = client("places_search.json")
    assert c.search("Mysuru palace") == c.search("Mysuru palace")
    assert len(t.calls) == 1
    c.search("something else")
    assert len(t.calls) == 2


def test_places_cache_expires():
    now = [1000.0]
    c, t = client("places_search.json", MemoryCache(lambda: now[0]))
    c.search("x")
    now[0] += 24 * 3600 + 1
    c.search("x")
    assert len(t.calls) == 2


def test_places_details_masks_and_hours():
    c, t = client("places_details.json")
    p = c.details("ChIJsampleMysorePalace0001")
    assert t.calls[0][2]["X-Goog-FieldMask"] == DETAILS_MASK
    assert t.calls[0][0] == "GET" and t.calls[0][1].endswith("/places/ChIJsampleMysorePalace0001")
    h = c.details("ChIJsampleMysorePalace0001", with_hours=True)
    assert t.calls[1][2]["X-Goog-FieldMask"] == HOURS_MASK
    assert [(o.day, o.opens.hour, o.closes.minute) for o in h.opening_hours] == [
        ("mon", 10, 30),
        ("tue", 10, 30),
    ]
    assert p.id == h.id


def test_places_nearby_emergency():
    c, t = client("places_nearby.json")
    (p,) = c.nearby_emergency(12.30, 76.65, "hospital")
    assert p.category == "hospital"
    _, url, headers, body, _ = t.calls[0]
    assert url.endswith("/places:searchNearby")
    assert headers["X-Goog-FieldMask"] == LIST_MASK
    assert body["includedTypes"] == ["hospital"]
    with pytest.raises(ValueError):
        c.nearby_emergency(12.3, 76.6, "bank")


def test_places_empty_result():
    c, t = client("places_search.json")
    t.payload = {}
    assert c.search("nowhere") == []
