"""Compare transport for one trip leg: the best rail, road and air option by A*
over the multimodal graph, ranked by time, cost and changes.

Each mode searches its own slice of the graph: road is car door to door; rail
and air may use walks and short road transfers to reach a station or airport.
Rail uses the sample timetable subset, road the Routes API (or the haversine
fake), air Google Flights through SerpApi when SERPAPI_API_KEY is set (cached
and capped; the fake air network otherwise, or for a pair the cap or an error
leaves without an answer). Air options carry seller offers."""
from __future__ import annotations

import datetime as dt
import hashlib
import math
from dataclasses import dataclass, replace
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from ty_contracts import (
    CityRef,
    CompareRequest,
    CompareResponse,
    Mode,
    RankedOption,
    TransportOption,
    Unavailable,
)
from ty_contracts.models import RankBy

from .flights import Flight, FlightProvider, default_flight_provider
from .graph import (
    COMFORT,
    DATA_DIR,
    KIND_AIRPORT,
    KIND_PLACE,
    KIND_STATION,
    AirEdgeProvider,
    Edge,
    FakeAirProvider,
    Graph,
    Node,
    RoadEdgeProvider,
    add_air,
    add_airport_transfers,
    add_places,
    add_road,
    add_station_transfers,
    haversine_km,
    load_rail,
)
from .roads import REF as ROUTES_API_REF
from .roads import default_road_provider
from .search import Weights, _result, astar
from .sellers import FlightQuery, flight_offers
from .sellers import Found as Quote

WEIGHTS = Weights(alpha=1.0, beta=0.0, gamma=30.0)  # minutes, plus 30 min per change
CHANGE_WEIGHT = 0.25  # balanced score: one change counts as a quarter of the best time or cost
MODE_ORDER = {Mode.rail: 0, Mode.road: 1, Mode.air: 2}
SEATS_PER_CAR = 4  # road fares are per vehicle; rail and air fares are per person
AIRPORT_KM = 60  # airports considered for a city
AIRPORT_MIN = 60  # at the airport before a live flight departs; part of the flight leg
INR_PER_MIN = 10.0  # picking a flight: arriving a minute earlier is worth this much fare (reversible guess)

# Sample city points (centre coordinates, approximate). Aliases map to one key.
CITIES: dict[str, tuple[str, float, float]] = {
    "bengaluru": ("Bengaluru", 12.9716, 77.5946),
    "mysuru": ("Mysuru", 12.2958, 76.6394),
    "panaji": ("Panaji", 15.4909, 73.8278),
    "madgaon": ("Madgaon", 15.2832, 73.9862),
    "mumbai": ("Mumbai", 18.9398, 72.8355),
    "pune": ("Pune", 18.5204, 73.8567),
    "kochi": ("Kochi", 9.9312, 76.2673),
    "chennai": ("Chennai", 13.0827, 80.2707),
    "hyderabad": ("Hyderabad", 17.3850, 78.4867),
    "mangaluru": ("Mangaluru", 12.9141, 74.8560),
    "hubballi": ("Hubballi", 15.3647, 75.1240),
    "thiruvananthapuram": ("Thiruvananthapuram", 8.5241, 76.9366),
    "vijayawada": ("Vijayawada", 16.5062, 80.6480),
    "coorg": ("Coorg", 12.4244, 75.7382),  # Madikeri, the district town
    "hampi": ("Hampi", 15.3350, 76.4600),
    "chikkamagaluru": ("Chikkamagaluru", 13.3161, 75.7720),
}
ALIASES = {
    "bangalore": "bengaluru", "mysore": "mysuru", "goa": "panaji", "panjim": "panaji",
    "margao": "madgaon", "bombay": "mumbai", "cochin": "kochi", "madras": "chennai",
    "mangalore": "mangaluru", "hubli": "hubballi", "trivandrum": "thiruvananthapuram",
    "madikeri": "coorg", "kodagu": "coorg", "chikmagalur": "chikkamagaluru",
}


class UnknownPlace(ValueError):
    pass


def resolve_city(name: str) -> Node:
    key = " ".join(name.lower().replace(",", " ").split())
    key = ALIASES.get(key, key)
    if key not in CITIES:
        raise UnknownPlace(f"unknown place {name!r}; known: {', '.join(v[0] for v in CITIES.values())}")
    label, lat, lon = CITIES[key]
    return Node(f"PL:{key}", KIND_PLACE, label, lat, lon)


def _keeps(mode: Mode, g: Graph, e: Edge) -> bool:
    kinds = {g.nodes[e.src].kind, g.nodes[e.dst].kind}
    if mode is Mode.road:
        return e.mode == "road" and kinds == {KIND_PLACE}
    hub = KIND_STATION if mode is Mode.rail else KIND_AIRPORT
    return e.mode in (mode.value, "walk") or (e.mode == "road" and kinds == {KIND_PLACE, hub})


def _slice(g: Graph, mode: Mode) -> Graph:
    return Graph(nodes=g.nodes, adj={n: [e for e in es if _keeps(mode, g, e)] for n, es in g.adj.items()})


def _merge(edges: tuple[Edge, ...]) -> tuple[Edge, ...]:
    """Join consecutive edges on the same vehicle (same mode and ref) into one leg."""
    out: list[Edge] = []
    for e in edges:
        if out and (out[-1].mode, out[-1].ref) == (e.mode, e.ref):
            p = out[-1]
            mins = p.minutes + e.minutes
            comfort = (p.comfort * p.minutes + e.comfort * e.minutes) / mins if mins else p.comfort
            out[-1] = Edge(p.src, e.dst, p.mode, mins, p.cost_inr + e.cost_inr, comfort, p.ref)
        else:
            out.append(e)
    return tuple(out)


def _label(n: Node) -> str:
    return f"{n.name} airport ({n.id[3:]})" if n.kind == KIND_AIRPORT else n.name


def _source(e: Edge, live: dict[str, Flight]) -> str:
    if e.mode == "rail":
        return "sample_rail"
    if e.mode == "air":
        return "serpapi_flights" if e.ref in live else "fake_air"
    if e.mode == "road":
        return "routes_api" if e.ref == ROUTES_API_REF else "haversine"
    return "walk"


def _party_cost(e: Edge, travellers: int) -> Edge:
    if e.mode in ("rail", "air"):
        return replace(e, cost_inr=e.cost_inr * travellers)
    if e.mode == "road":
        return replace(e, cost_inr=e.cost_inr * math.ceil(travellers / SEATS_PER_CAR))
    return e


def option_id(opt: TransportOption) -> str:
    key = "|".join(f"{leg.from_}>{leg.to}:{leg.mode}:{leg.depart.isoformat()}:{leg.minutes}" for leg in opt.legs)
    return f"{opt.mode}-{hashlib.sha256(key.encode()).hexdigest()[:12]}"


@dataclass
class Found:
    mode: Mode
    option: TransportOption
    changes: int
    sources: list[str]


class CompareService:
    def __init__(self, road: RoadEdgeProvider | None = None, air: AirEdgeProvider | None = None,
                 data_dir: Path = DATA_DIR, flights: FlightProvider | None = None, live: bool = True) -> None:
        self.road = road if road is not None else default_road_provider()
        self.air = air if air is not None else FakeAirProvider()
        self.flights = flights if flights is not None else (default_flight_provider() if live else None)
        self.base = Graph()
        load_rail(self.base, data_dir)
        add_air(self.base, self.air)

    def _graph_for(self, places: list[Node]) -> Graph:
        g = Graph(nodes=dict(self.base.nodes), adj={k: list(v) for k, v in self.base.adj.items()})
        add_places(g, places)
        add_road(g, self.road, places)
        add_airport_transfers(g, self.road)
        add_station_transfers(g, self.road)
        return g

    def _near_airports(self, g: Graph, p: Node) -> list[Node]:
        return [a for a in g.nodes_of(KIND_AIRPORT) if haversine_km(p.lat, p.lon, a.lat, a.lon) <= AIRPORT_KM]

    def _live_air(self, g: Graph, src: Node, dst: Node, day: dt.date, start: dt.datetime) -> dict[str, Flight]:
        """Swap the estimated flights for one live flight per airport pair near src
        and dst: of the flights you can reach, the best on arrival time plus fare. A pair with no live answer (no key, cap,
        error) keeps its estimate; a pair with no reachable flight that day has
        none; estimated connections through other airports are dropped."""
        chosen: dict[str, Flight] = {}
        if self.flights is None:
            return chosen
        estimated: set[tuple[str, str]] = set()
        for a in self._near_airports(g, src):
            for b in self._near_airports(g, dst):
                if a.id == b.id:
                    continue
                found = self.flights.flights(a.id[3:], b.id[3:], day)
                if found is None:
                    estimated.add((a.id, b.id))
                    continue
                ground = self.road.road_edge(src, a)
                ready = start + timedelta(minutes=(ground.minutes if ground else 60) + AIRPORT_MIN)
                reachable = [f for f in found if f.depart >= ready]
                f = min(reachable, key=lambda f: ((f.arrive - start).total_seconds() / 60 + f.price_inr / INR_PER_MIN,
                                                  f.depart), default=None)
                if f is not None:
                    g.add_edge(Edge(a.id, b.id, "air", AIRPORT_MIN + f.minutes, float(f.price_inr),
                                    COMFORT["air"], ref=f.number))
                    chosen[f.number] = f
        for n, es in g.adj.items():
            g.adj[n] = [e for e in es if e.mode != "air" or e.ref in chosen or (e.src, e.dst) in estimated]
        return chosen

    def _find(self, g: Graph, src: Node, dst: Node, mode: Mode, start: dt.datetime,
              travellers: int = 1, live: dict[str, Flight] | None = None) -> Found | None:
        live = live or {}
        res = astar(_slice(g, mode), src.id, dst.id, WEIGHTS, start=start)
        if res is None:
            return None
        # one leg per vehicle, built by the same code as search
        merged = tuple(_party_cost(e, travellers) for e in _merge(res.edges))
        opt = _result(merged, res.objective, res.expansions, start).option
        legs = [leg.model_copy(update={"from_": _label(g.nodes[e.src]), "to": _label(g.nodes[e.dst])})
                for leg, e in zip(opt.legs, merged, strict=True)]
        stops, offers = 0, []
        air = next((i for i, e in enumerate(merged) if e.mode == "air"), None)
        if air is not None:
            e = merged[air]
            f = live.get(e.ref)
            if f is not None:  # shift the trip so the flight leg starts AIRPORT_MIN before take-off
                shift = (f.depart - timedelta(minutes=AIRPORT_MIN)) - legs[air].depart
                legs = [leg.model_copy(update={"depart": leg.depart + shift, "arrive": leg.arrive + shift})
                        for leg in legs]
                stops = f.stops
            quotes = [Quote(q.seller, q.price_inr * travellers) for q in self.flights.booking(f)] if f else []
            offers = flight_offers(FlightQuery(e.src[3:], e.dst[3:], start.date(), travellers), quotes)
        opt = opt.model_copy(update={"mode": mode, "legs": legs, "offers": offers})
        rides = [e for e in merged if e.mode != "walk"]
        sources = sorted({_source(e, live) for e in merged})
        return Found(mode, opt, max(0, len(rides) - 1) + stops, sources)

    def _why_not(self, g: Graph, src: Node, dst: Node, mode: Mode) -> str:
        if mode is Mode.air:
            for p in (src, dst):
                if not any(haversine_km(p.lat, p.lon, a.lat, a.lon) <= 60 for a in g.nodes_of(KIND_AIRPORT)):
                    return f"no airport within 60 km of {p.name}"
            return f"no flight between the airports near {src.name} and {dst.name}"
        if mode is Mode.rail:
            return f"no train in the rail subset links {src.name} and {dst.name}"
        return f"no road route found between {src.name} and {dst.name}"

    def compare(self, req: CompareRequest) -> CompareResponse:
        src, dst = resolve_city(req.origin), resolve_city(req.destination)
        if src.id == dst.id:
            raise UnknownPlace("origin and destination are the same place")
        day = req.date or dt.date.today()
        start = dt.datetime.combine(day, req.depart_time)
        g = self._graph_for([src, dst])
        live = self._live_air(g, src, dst, day, start) if Mode.air in req.modes else {}
        found, unavailable = [], []
        for mode in sorted(set(req.modes), key=MODE_ORDER.get):
            f = self._find(g, src, dst, mode, start, req.travellers, live)
            if f:
                found.append(f)
            else:
                unavailable.append(Unavailable(mode=mode, reason=self._why_not(g, src, dst, mode)))
        return CompareResponse(
            origin=CityRef(name=src.name, lat=src.lat, lng=src.lon),
            destination=CityRef(name=dst.name, lat=dst.lat, lng=dst.lon),
            date=day, rank_by=req.rank_by, options=rank(found, req.rank_by), unavailable=unavailable,
            notes=["Rail uses sample timetables; waits for departures are not modelled yet.", _air_note(found)],
        )


def _air_note(found: list[Found]) -> str:
    if any("serpapi_flights" in f.sources for f in found):
        return ("Air uses Google Flights fares (economy, via SerpApi, cached up to 6 hours) for the reachable "
                f"flight best on arrival time and fare; the flight leg includes {AIRPORT_MIN} min at the airport.")
    return "Air uses estimated fares and times; seller links search the same route and date."


def rank(found: list[Found], rank_by: RankBy) -> list[RankedOption]:
    if not found:
        return []
    best_t = min(f.option.total_minutes for f in found) or 1
    best_c = min(f.option.total_cost_inr for f in found) or 1

    def score(f: Found) -> float:
        return f.option.total_minutes / best_t + f.option.total_cost_inr / best_c + CHANGE_WEIGHT * f.changes

    keys = {
        "balanced": lambda f: (score(f), MODE_ORDER[f.mode]),
        "time": lambda f: (f.option.total_minutes, f.option.total_cost_inr, MODE_ORDER[f.mode]),
        "cost": lambda f: (f.option.total_cost_inr, f.option.total_minutes, MODE_ORDER[f.mode]),
        "changes": lambda f: (f.changes, f.option.total_minutes, MODE_ORDER[f.mode]),
    }
    ordered = sorted(found, key=keys[rank_by])
    return [RankedOption(id=option_id(f.option), rank=i, changes=f.changes, score=round(score(f), 3), sources=f.sources, option=f.option)
            for i, f in enumerate(ordered, 1)]


@lru_cache(maxsize=1)
def get_service() -> CompareService:
    return CompareService()
