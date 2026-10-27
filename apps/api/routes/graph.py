"""Multimodal transport graph: stations, airports and city points joined by
rail, road, air and walk edges. Stdlib only; offline fakes for road and air."""
from __future__ import annotations

import gzip
import itertools
import json
import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

DATA_DIR = Path(__file__).resolve().parent / "data"

# Reversible assumptions (offline fakes, replaced by live providers later).
RAIL_INR_PER_KM = 0.6
ROAD_KMH = 45.0
ROAD_DETOUR = 1.3
RAIL_DETOUR = 1.15
ROAD_INR_PER_KM = 6.0
WALK_KMH = 4.5
AIR_CRUISE_KMH = 750.0
AIR_OVERHEAD_MIN = 45
AIR_BASE_INR = 2500.0
AIR_INR_PER_KM = 4.5
COMFORT = {"rail": 0.7, "road": 0.5, "air": 0.8, "walk": 0.3}  # 0..1, higher is better

KIND_STATION, KIND_AIRPORT, KIND_PLACE = "station", "airport", "place"


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    mode: str  # rail | road | air | walk
    minutes: float
    cost_inr: float
    comfort: float
    ref: str = ""  # train number, flight hint, etc.


def haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


class RoadEdgeProvider(Protocol):
    def road_edge(self, a: Node, b: Node) -> Edge | None: ...


class AirEdgeProvider(Protocol):
    def airports(self) -> list[Node]: ...
    def air_edge(self, a: Node, b: Node) -> Edge | None: ...


class HaversineRoadProvider:
    """Offline fake: great-circle x 1.3 at 45 km/h."""

    def __init__(self, max_km: float = 800.0) -> None:
        self.max_km = max_km

    def road_edge(self, a: Node, b: Node) -> Edge | None:
        km = haversine_km(a.lat, a.lon, b.lat, b.lon) * ROAD_DETOUR
        if km > self.max_km:
            return None
        return Edge(a.id, b.id, "road", km / ROAD_KMH * 60, km * ROAD_INR_PER_KM, COMFORT["road"])


AIRPORTS = [
    ("BLR", "Bengaluru", 13.1986, 77.7066),
    ("GOI", "Goa (Dabolim)", 15.3808, 73.8314),
    ("BOM", "Mumbai", 19.0896, 72.8656),
    ("PNQ", "Pune", 18.5821, 73.9197),
    ("COK", "Kochi", 10.1520, 76.4019),
    ("TRV", "Thiruvananthapuram", 8.4821, 76.9201),
    ("MAA", "Chennai", 12.9941, 80.1709),
    ("HYD", "Hyderabad", 17.2403, 78.4294),
    ("VGA", "Vijayawada", 16.5304, 80.7968),
    ("IXE", "Mangaluru", 12.9613, 74.8901),
    ("GOX", "Goa (Mopa)", 15.7444, 73.8606),
    ("VDY", "Vidyanagar (Ballari)", 15.1750, 76.6349),
]


class FakeAirProvider:
    """Offline fake: small airport list, block time = overhead + distance / 750 km/h."""

    def __init__(self, min_km: float = 250.0) -> None:
        self.min_km = min_km
        self._nodes = [Node(f"AP:{c}", KIND_AIRPORT, n, la, lo) for c, n, la, lo in AIRPORTS]

    def airports(self) -> list[Node]:
        return list(self._nodes)

    def air_edge(self, a: Node, b: Node) -> Edge | None:
        km = haversine_km(a.lat, a.lon, b.lat, b.lon)
        if km < self.min_km:
            return None
        return Edge(a.id, b.id, "air", AIR_OVERHEAD_MIN + km / AIR_CRUISE_KMH * 60,
                    AIR_BASE_INR + km * AIR_INR_PER_KM, COMFORT["air"], ref=f"{a.id[3:]}-{b.id[3:]}")


@dataclass
class Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    adj: dict[str, list[Edge]] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        self.nodes.setdefault(node.id, node)
        self.adj.setdefault(node.id, [])

    def add_edge(self, edge: Edge) -> None:
        if edge.src not in self.nodes or edge.dst not in self.nodes:
            raise KeyError(f"unknown node in edge {edge.src}->{edge.dst}")
        self.adj[edge.src].append(edge)

    def neighbors(self, node_id: str) -> list[Edge]:
        return self.adj.get(node_id, [])

    def edges(self) -> Iterable[Edge]:
        for lst in self.adj.values():
            yield from lst

    def edge_counts(self) -> dict[str, int]:
        return dict(Counter(e.mode for e in self.edges()))

    def nodes_of(self, kind: str) -> list[Node]:
        return [n for n in self.nodes.values() if n.kind == kind]


def _read_json(name: str, data_dir: Path):
    plain, gz = data_dir / f"{name}.json", data_dir / f"{name}.json.gz"
    if gz.exists():
        return json.loads(gzip.decompress(gz.read_bytes()))
    return json.loads(plain.read_text(encoding="utf-8"))


def load_rail(graph: Graph, data_dir: Path = DATA_DIR) -> None:
    """Add station nodes and one rail edge per consecutive stop pair of each train."""
    stations = _read_json("rail_stations", data_dir)
    trains = _read_json("rail_trains", data_dir)
    for s in stations:
        graph.add_node(Node(f"ST:{s['code']}", KIND_STATION, s["name"], s["lat"], s["lon"]))
    for t in trains:
        stops = t["stops"]
        for a, b in itertools.pairwise(stops):
            dep = a["dep"] if a["dep"] is not None else a["arr"]
            arr = b["arr"] if b["arr"] is not None else b["dep"]
            if dep is None or arr is None:
                continue
            minutes = (b["day"] - a["day"]) * 1440 + arr - dep
            if minutes <= 0:
                continue
            na, nb = graph.nodes.get(f"ST:{a['code']}"), graph.nodes.get(f"ST:{b['code']}")
            if na is None or nb is None:
                continue
            km = haversine_km(na.lat, na.lon, nb.lat, nb.lon) * RAIL_DETOUR
            graph.add_edge(Edge(na.id, nb.id, "rail", float(minutes), km * RAIL_INR_PER_KM,
                                COMFORT["rail"], ref=t["number"]))


def add_places(graph: Graph, places: Iterable[Node], walk_km: float = 5.0) -> None:
    """Add city/place points and walk edges to stations/airports within walk_km."""
    places = list(places)
    for p in places:
        graph.add_node(p)
    hubs = graph.nodes_of(KIND_STATION) + graph.nodes_of(KIND_AIRPORT)
    for p in places:
        for h in hubs:
            km = haversine_km(p.lat, p.lon, h.lat, h.lon)
            if km <= walk_km:
                m = km / WALK_KMH * 60
                graph.add_edge(Edge(p.id, h.id, "walk", m, 0.0, COMFORT["walk"]))
                graph.add_edge(Edge(h.id, p.id, "walk", m, 0.0, COMFORT["walk"]))


def add_road(graph: Graph, provider: RoadEdgeProvider, nodes: Iterable[Node] | None = None) -> None:
    pool = list(nodes) if nodes is not None else [n for n in graph.nodes.values() if n.kind != KIND_AIRPORT]
    for a in pool:
        for b in pool:
            if a.id != b.id:
                e = provider.road_edge(a, b)
                if e:
                    graph.add_edge(e)


def add_airport_transfers(graph: Graph, provider: RoadEdgeProvider, max_km: float = 60.0) -> None:
    """Road transfers between place points and airports within max_km (great-circle),
    so flights are reachable from the ground network."""
    for p in graph.nodes_of(KIND_PLACE):
        for ap in graph.nodes_of(KIND_AIRPORT):
            if haversine_km(p.lat, p.lon, ap.lat, ap.lon) <= max_km:
                for a, b in ((p, ap), (ap, p)):
                    e = provider.road_edge(a, b)
                    if e:
                        graph.add_edge(e)


def add_station_transfers(graph: Graph, provider: RoadEdgeProvider, max_km: float = 40.0) -> None:
    """Road transfers between place points and stations within max_km (great-circle),
    for stations too far to walk to."""
    for p in graph.nodes_of(KIND_PLACE):
        for st in graph.nodes_of(KIND_STATION):
            if haversine_km(p.lat, p.lon, st.lat, st.lon) <= max_km:
                for a, b in ((p, st), (st, p)):
                    e = provider.road_edge(a, b)
                    if e:
                        graph.add_edge(e)


def add_air(graph: Graph, provider: AirEdgeProvider) -> None:
    aps = provider.airports()
    for ap in aps:
        graph.add_node(ap)
    for a in aps:
        for b in aps:
            if a.id != b.id:
                e = provider.air_edge(a, b)
                if e:
                    graph.add_edge(e)


def build_graph(
    data_dir: Path = DATA_DIR,
    places: Iterable[Node] = (),
    road: RoadEdgeProvider | None = None,
    air: AirEdgeProvider | None = None,
) -> Graph:
    g = Graph()
    load_rail(g, data_dir)
    if air is not None:
        add_air(g, air)
    add_places(g, places)
    if road is not None:
        # road links between place points only, keeps the edge count small
        add_road(g, road, [n for n in g.nodes.values() if n.kind == KIND_PLACE])
        add_airport_transfers(g, road)
    return g
