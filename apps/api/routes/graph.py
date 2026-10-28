"""Multimodal transport graph: stations, airports and city points joined by
rail, road, air and walk edges. Stdlib only; offline fakes for road and air."""
from __future__ import annotations

import gzip
import itertools
import json
import math
import os
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

DATA_DIR = Path(__file__).resolve().parent / "data"
SAMPLE_RAIL_DIR = DATA_DIR / "sample"  # fictional trains 90001-90014: fallback and small unit tests


def rail_dir() -> Path:
    """The datameet corridor subset in data/, or the sample when ROUTES_RAIL=sample
    or the subset is missing."""
    if os.environ.get("ROUTES_RAIL") == "sample":
        return SAMPLE_RAIL_DIR
    if any((DATA_DIR / f"rail_trains.json{ext}").exists() for ext in ("", ".gz")):
        return DATA_DIR
    return SAMPLE_RAIL_DIR

# Reversible assumptions (offline fakes, replaced by live providers later).
RAIL_INR_PER_KM = 0.6  # graph edges only (search tests); options are priced by fares.py
ROAD_KMH = 45.0
ROAD_DETOUR = 1.3
CITY_KM = 30.0  # shorter road trips run at city speed
CITY_KMH = 22.0  # city traffic, door to door
CITY_DETOUR = 1.4  # city streets wind more than highways
PARK_MIN = 5  # finding the cab, parking, walking to the door
WALK_ROAD_KM = 0.8  # shorter than this, walk
RAIL_DETOUR = 1.15
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
    km: float = 0.0  # road and walk: distance on the ground


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


def city_or_road(km_line: float) -> tuple[str, float, float]:
    """(mode, km, minutes) on the ground for a straight-line distance: a walk when short,
    city streets at city speed (plus PARK_MIN) under CITY_KM, else the highway."""
    city = km_line * CITY_DETOUR
    if city <= WALK_ROAD_KM:
        return "walk", city, city / WALK_KMH * 60
    if city < CITY_KM:
        return "road", city, PARK_MIN + city / CITY_KMH * 60
    km = km_line * ROAD_DETOUR
    return "road", km, PARK_MIN + km / ROAD_KMH * 60


class HaversineRoadProvider:
    """Offline fake: a walk under WALK_ROAD_KM, city streets (x 1.4 at 22 km/h plus 5 min)
    under CITY_KM, else the highway (great-circle x 1.3 at 45 km/h). Cost: one cab's fare."""

    def __init__(self, max_km: float = 800.0) -> None:
        self.max_km = max_km

    def road_edge(self, a: Node, b: Node) -> Edge | None:
        from .fares import cab_fare

        mode, km, minutes = city_or_road(haversine_km(a.lat, a.lon, b.lat, b.lon))
        if km > self.max_km:
            return None
        cost = 0.0 if mode == "walk" else float(cab_fare(km))
        return Edge(a.id, b.id, mode, minutes, cost, COMFORT[mode], km=km)


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
    ("MYQ", "Mysuru (Mandakalli)", 12.2300, 76.6558),
    ("DEL", "Delhi", 28.5562, 77.1000),
    ("JAI", "Jaipur", 26.8242, 75.8122),
    ("AGR", "Agra", 27.1558, 77.9609),
    ("CCU", "Kolkata", 22.6547, 88.4467),
    ("AMD", "Ahmedabad", 23.0772, 72.6347),
    ("LKO", "Lucknow", 26.7606, 80.8893),
    ("VNS", "Varanasi", 25.4524, 82.8593),
    ("ATQ", "Amritsar", 31.7096, 74.7973),
    ("UDR", "Udaipur", 24.6177, 73.8961),
    ("JDH", "Jodhpur", 26.2511, 73.0489),
    ("BHO", "Bhopal", 23.2875, 77.3374),
    ("IDR", "Indore", 22.7218, 75.8011),
    ("NAG", "Nagpur", 21.0922, 79.0472),
    ("RPR", "Raipur", 21.1804, 81.7388),
    ("PAT", "Patna", 25.5913, 85.0880),
    ("IXR", "Ranchi", 23.3143, 85.3217),
    ("BBI", "Bhubaneswar", 20.2444, 85.8178),
    ("GAU", "Guwahati", 26.1061, 91.5859),
    ("IXC", "Chandigarh", 30.6735, 76.7885),
    ("DED", "Dehradun", 30.1897, 78.1803),
    ("SXR", "Srinagar", 33.9871, 74.7742),
    ("STV", "Surat", 21.1141, 72.7418),
    ("BDQ", "Vadodara", 22.3362, 73.2263),
    ("IXU", "Aurangabad", 19.8627, 75.3981),
    ("VTZ", "Visakhapatnam", 17.7212, 83.2245),
    ("TIR", "Tirupati", 13.6325, 79.5433),
    ("CJB", "Coimbatore", 11.0300, 77.0434),
    ("IXM", "Madurai", 9.8345, 78.0934),
    ("TRZ", "Tiruchirappalli", 10.7654, 78.7097),
    ("CCJ", "Kozhikode", 11.1368, 75.9553),
    ("HBX", "Hubballi", 15.3617, 75.0849),
    ("IXG", "Belagavi", 15.8593, 74.6183),
]


class FakeAirProvider:
    """Offline fake: small airport list, block time = overhead + distance / 750 km/h."""

    def __init__(self, min_km: float = 200.0) -> None:
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


def load_rail(graph: Graph, data_dir: Path | None = None) -> None:
    """Add station nodes and one rail edge per consecutive stop pair of each train."""
    data_dir = data_dir or rail_dir()
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
    data_dir: Path | None = None,
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
