import json

import pytest

from routes.graph import (
    KIND_PLACE,
    FakeAirProvider,
    HaversineRoadProvider,
    Node,
    build_graph,
    haversine_km,
)


@pytest.fixture(autouse=True)
def sample_rail(monkeypatch):
    """These tests cover the logic on the small fictional sample network."""
    monkeypatch.setenv("ROUTES_RAIL", "sample")


CITIES = [
    Node("PL:blr", KIND_PLACE, "Bengaluru", 12.9716, 77.5946),
    Node("PL:goa", KIND_PLACE, "Madgaon", 15.2700, 73.9580),
    Node("PL:mum", KIND_PLACE, "Mumbai", 18.9400, 72.8350),
]


def reachable(g, start, mode="rail"):
    seen, stack = {start}, [start]
    while stack:
        for e in g.neighbors(stack.pop()):
            if e.mode == mode and e.dst not in seen:
                seen.add(e.dst)
                stack.append(e.dst)
    return seen


def test_key_stations_exist():
    g = build_graph()
    assert "ST:SBC" in g.nodes and "ST:MAO" in g.nodes


def test_rail_path_bengaluru_madgaon():
    g = build_graph()
    assert "ST:MAO" in reachable(g, "ST:SBC")


def test_rail_edges_positive_and_costed():
    g = build_graph()
    rail = [e for e in g.edges() if e.mode == "rail"]
    assert rail and all(e.minutes > 0 and e.cost_inr > 0 for e in rail)


def test_full_graph_edge_counts():
    g = build_graph(places=CITIES, road=HaversineRoadProvider(), air=FakeAirProvider())
    counts = g.edge_counts()
    print("edge counts:", json.dumps(counts, sort_keys=True))
    assert {"rail", "road", "air", "walk"} <= set(counts)
    assert "AP:BLR" in g.nodes and "AP:GOI" in g.nodes


def test_road_fake_formula():
    a, b = CITIES[0], CITIES[1]
    e = HaversineRoadProvider().road_edge(a, b)
    km = haversine_km(a.lat, a.lon, b.lat, b.lon) * 1.3
    assert abs(e.minutes - (5 + km / 45 * 60)) < 1e-6 and e.mode == "road" and e.km == pytest.approx(km)


def test_road_fake_is_city_realistic_for_short_hops():
    """Stop to stop in a city: city speed plus 5 min and a cab fare, never "Rs 1, under a minute";
    a few hundred metres is a free walk. Mysore Palace to Chamundeshwari is about 4 km as the crow flies."""
    road = HaversineRoadProvider()
    palace = Node("PL:p", KIND_PLACE, "Mysore Palace", 12.3051, 76.6551)
    hill = Node("PL:h", KIND_PLACE, "Chamundeshwari", 12.2724, 76.6702)
    e = road.road_edge(palace, hill)
    assert e.mode == "road" and 15 <= e.minutes <= 30 and e.cost_inr >= 100
    gate = Node("PL:g", KIND_PLACE, "Palace gate", 12.3070, 76.6551)
    w = road.road_edge(palace, gate)
    assert w.mode == "walk" and w.cost_inr == 0 and w.minutes >= 1


def test_air_fake_skips_short_hops():
    air = FakeAirProvider()
    n = {x.id: x for x in air.airports()}
    assert air.air_edge(n["AP:BLR"], n["AP:GOI"]).mode == "air"
    assert air.air_edge(n["AP:BOM"], n["AP:PNQ"]) is None


def test_airports_reachable_from_places():
    g = build_graph(places=CITIES, road=HaversineRoadProvider(), air=FakeAirProvider())
    seen, stack = {"PL:blr"}, ["PL:blr"]
    while stack:
        for e in g.neighbors(stack.pop()):
            if e.dst not in seen:
                seen.add(e.dst)
                stack.append(e.dst)
    assert "AP:BLR" in seen and "AP:GOI" in seen
    assert any(e.mode == "road" and e.src == "AP:GOI" and e.dst == "PL:goa" for e in g.edges())
