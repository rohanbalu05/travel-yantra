import json
import logging

from routes.graph import (KIND_PLACE, Edge, FakeAirProvider, HaversineRoadProvider, Node,
                          build_graph, haversine_km)

log = logging.getLogger(__name__)
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


def test_full_graph_edge_counts(capsys):
    g = build_graph(places=CITIES, road=HaversineRoadProvider(), air=FakeAirProvider())
    counts = g.edge_counts()
    print("edge counts:", json.dumps(counts, sort_keys=True))
    assert {"rail", "road", "air", "walk"} <= set(counts)
    assert "AP:BLR" in g.nodes and "AP:GOI" in g.nodes


def test_road_fake_formula():
    a, b = CITIES[0], CITIES[1]
    e = HaversineRoadProvider().road_edge(a, b)
    km = haversine_km(a.lat, a.lon, b.lat, b.lon) * 1.3
    assert abs(e.minutes - km / 45 * 60) < 1e-6 and e.mode == "road"


def test_air_fake_skips_short_hops():
    air = FakeAirProvider()
    n = {x.id: x for x in air.airports()}
    assert air.air_edge(n["AP:BLR"], n["AP:GOI"]).mode == "air"
    assert air.air_edge(n["AP:BOM"], n["AP:PNQ"]) is None
