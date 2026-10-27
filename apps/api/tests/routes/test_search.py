import itertools
import random

import pytest

from routes.graph import (
    KIND_PLACE,
    SAMPLE_RAIL_DIR,
    FakeAirProvider,
    HaversineRoadProvider,
    Node,
    build_graph,
)
from routes.search import Weights, astar, dijkstra


@pytest.fixture(autouse=True)
def sample_rail(monkeypatch):
    """These tests cover the logic on the small fictional sample network."""
    monkeypatch.setenv("ROUTES_RAIL", "sample")


PLACES = [
    Node("PL:blr", KIND_PLACE, "Bengaluru", 12.9716, 77.5946),
    Node("PL:goa", KIND_PLACE, "Madgaon", 15.2700, 73.9580),
    Node("PL:mum", KIND_PLACE, "Mumbai", 18.9400, 72.8350),
    Node("PL:mys", KIND_PLACE, "Mysuru", 12.2958, 76.6394),
    Node("PL:hyd", KIND_PLACE, "Hyderabad", 17.3850, 78.4867),
    Node("PL:kochi", KIND_PLACE, "Kochi", 9.9312, 76.2673),
]
MIXES = [Weights(1, 0, 0), Weights(0, 1, 0), Weights(1, 0.05, 30)]  # time, cost, mixed


@pytest.fixture(scope="module")
def g():
    return build_graph(SAMPLE_RAIL_DIR, places=PLACES, road=HaversineRoadProvider(), air=FakeAirProvider())


def test_time_only_prefers_air(g):
    r = dijkstra(g, "PL:blr", "PL:mum", MIXES[0])
    assert r.option.mode == "air" and r.option.total_minutes < 400
    assert r.option.legs[0].from_ == "PL:blr" and r.option.legs[-1].to == "PL:mum"


def test_cost_only_cheaper_than_time(g):
    t = dijkstra(g, "PL:blr", "PL:goa", MIXES[0]).option
    c = dijkstra(g, "PL:blr", "PL:goa", MIXES[1]).option
    assert c.total_cost_inr <= t.total_cost_inr and c.total_minutes >= t.total_minutes


def test_mixed_objective_matches_edges(g):
    w = MIXES[2]
    r = astar(g, "PL:mys", "PL:hyd", w)
    es = r.edges
    transfers = sum(1 for a, b in itertools.pairwise(es) if (a.mode, a.ref) != (b.mode, b.ref))
    expected = sum(w.alpha * e.minutes + w.beta * e.cost_inr for e in es) + w.gamma * transfers
    assert r.objective == pytest.approx(expected)


def test_unknown_node(g):
    assert astar(g, "PL:blr", "nope") is None


def test_same_node_has_no_option(g):
    assert dijkstra(g, "PL:blr", "PL:blr") is None
    assert astar(g, "PL:blr", "PL:blr") is None


def test_astar_matches_dijkstra_and_expands_less(g):
    rng = random.Random(7)
    ids = [p.id for p in PLACES]
    dj = a_s = 0
    for i in range(20):
        a, b = rng.sample(ids, 2)
        d, s = dijkstra(g, a, b, MIXES[i % 3]), astar(g, a, b, MIXES[i % 3])
        assert d.objective == pytest.approx(s.objective)
        dj += d.expansions
        a_s += s.expansions
    print(f"avg expansions over 20 pairs: dijkstra={dj / 20:.1f} astar={a_s / 20:.1f}")
    assert a_s < dj
