"""Compare transport for one trip leg: the best rail, road and air option by A*
over the multimodal graph, ranked by time, cost and changes.

Road and air are A* over their slice of the graph: road is car door to door;
air may use walks and short road transfers to reach an airport. Rail is an
earliest-arrival search over real timetables (timetable.py, the datameet
corridor subset), with a road or walk transfer to and from the stations and
real departure times. Road uses the Routes API (or the haversine fake), air Google Flights through SerpApi when SERPAPI_API_KEY is set (cached
and capped; the fake air network otherwise, or for a pair the cap or an error
leaves without an answer). Air options carry seller offers."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, replace
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from ty_contracts import (
    CityRef,
    CompareRequest,
    CompareResponse,
    Leg,
    Mode,
    RankedOption,
    TransportOption,
    Unavailable,
)
from ty_contracts.models import RankBy

from .fares import FUEL_INR_PER_KM, cab_fare, drive_cost, rail_fare, toll
from .fares import rail_class as pick_class
from .flights import Flight, FlightProvider, default_flight_provider
from .graph import (
    COMFORT,
    DATA_DIR,
    KIND_AIRPORT,
    KIND_PLACE,
    KIND_STATION,
    RAIL_DETOUR,
    SAMPLE_RAIL_DIR,
    WALK_KMH,
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
    haversine_km,
    rail_dir,
)
from .roads import REF as ROUTES_API_REF
from .roads import default_road_provider
from .search import Weights, _result, astar
from .sellers import FlightQuery, flight_offers
from .sellers import Found as Quote
from .timetable import BOARD_MIN, Journey, Ride, get_timetable

WEIGHTS = Weights(alpha=1.0, beta=0.0, gamma=30.0)  # minutes, plus 30 min per change
CHANGE_WEIGHT = 0.25  # balanced score: one change counts as a quarter of the best time or cost
OVERNIGHT_PENALTY = 1.5  # balanced score: an overnight train when a daytime option exists (see _overnight_penalised)
SHORT_TRIP_MIN = 8 * 60  # a daytime option this fast makes the trip "short"
NIGHT_END_HOUR = 5  # a train moving between midnight and 05:00 is overnight
EGRESS_WEIGHT = 4  # choosing where to get off: a minute in a cab counts as four on the train
RAIL_CHANGE_MIN = 60  # picking one rail journey: each change between trains counts as an hour later
RAIL_CANDIDATES = 6  # journeys compared when picking one
MODE_ORDER = {Mode.rail: 0, Mode.road: 1, Mode.air: 2}
AIRPORT_KM = 60  # airports considered for a city
AIRPORT_MIN = 60  # at the airport before a live flight departs; part of the flight leg
MIN_FLIGHT_KM = 200  # airports closer than this: no flight looked up (Bengaluru-Mysuru is 140 km, -Ballari 247)
STATION_KM = 40  # stations considered for a city, by road
STATION_K = 3  # nearest served stations per city (each one a road edge, so a Routes API call)
WALK_KM = 1.0  # closer than this, walk to the station
MAX_DRIVE_MIN = 15 * 60  # a longer drive is not offered (Chennai-Delhi by road is about 38 h)
INR_PER_MIN = 10.0  # picking a flight: arriving a minute earlier is worth this much fare (reversible guess)

# City centre points (approximate) and aliases, shared with stays and the rail build: data/cities.json.
_CITY_DATA = json.loads((DATA_DIR / "cities.json").read_text(encoding="utf-8"))
CITIES: dict[str, tuple[str, float, float]] = {k: tuple(v) for k, v in _CITY_DATA["cities"].items()}
ALIASES: dict[str, str] = _CITY_DATA["aliases"]


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
            out[-1] = Edge(p.src, e.dst, p.mode, mins, p.cost_inr + e.cost_inr, comfort, p.ref, p.km + e.km)
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
    """The whole party's cost (fares.py): rail and air per person; a drive between two cities
    is fuel and tolls per car; any other road leg (to and from stations and airports) is a
    cab fare per cab; walks are free."""
    if e.mode in ("rail", "air"):
        return replace(e, cost_inr=e.cost_inr * travellers)
    if e.mode == "road":
        if e.src.startswith("PL:") and e.dst.startswith("PL:"):
            return replace(e, cost_inr=drive_cost(e.km, toll(e.src[3:], e.dst[3:]), travellers))
        return replace(e, cost_inr=cab_fare(e.km, travellers))
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
                 data_dir: Path | None = None, flights: FlightProvider | None = None, live: bool = True) -> None:
        """data_dir: the rail timetable folder (default: the datameet subset, see graph.rail_dir)."""
        self.road = road if road is not None else default_road_provider()
        self.air = air if air is not None else FakeAirProvider()
        self.flights = flights if flights is not None else (default_flight_provider() if live else None)
        self.timetable = get_timetable(data_dir)
        self.rail_source = "sample_rail" if (data_dir or rail_dir()) == SAMPLE_RAIL_DIR else "datameet_rail"
        self.base = Graph()
        add_air(self.base, self.air)

    def _graph_for(self, places: list[Node]) -> Graph:
        g = Graph(nodes=dict(self.base.nodes), adj={k: list(v) for k, v in self.base.adj.items()})
        add_places(g, places)
        add_road(g, self.road, places)
        add_airport_transfers(g, self.road)
        return g

    def _ground(self, a: Node, b: Node) -> Edge | None:
        km = haversine_km(a.lat, a.lon, b.lat, b.lon)
        if km <= WALK_KM:
            return Edge(a.id, b.id, "walk", km / WALK_KMH * 60, 0.0, COMFORT["walk"])
        return self.road.road_edge(a, b)

    def _station(self, code: str) -> Node:
        s = self.timetable.stations[code]
        return Node(f"ST:{code}", KIND_STATION, s["name"], s["lat"], s["lon"])

    def _ends(self, p: Node, outbound: bool) -> dict[str, Edge]:
        out = {}
        for code, _ in self.timetable.near(p.lat, p.lon, STATION_KM, STATION_K):
            st = self._station(code)
            e = self._ground(p, st) if outbound else self._ground(st, p)
            if e is not None:
                out[code] = e
        return out

    def _scan(self, start: dt.datetime, access: dict[str, Edge], egress: dict[str, Edge]) -> Journey | None:
        t0 = start.hour * 60 + start.minute
        board = {c: t0 + round(e.minutes) + BOARD_MIN for c, e in access.items()}
        # stay on the train to the station nearest the destination rather than race a cab from an earlier stop
        off = {c: round(e.minutes * (EGRESS_WEIGHT if e.mode == "road" else 1)) for c, e in egress.items()}
        j = (self.timetable.journey(board, off, start.date(), start.time(), night_end=NIGHT_END_HOUR * 60)
             if board and off else None)
        if j is None:
            return None
        # a first hop to a station you could reach by road anyway is just an early start
        rides = self._fewer_trains(j.rides, start, access)
        return Journey(rides[0].board, j.egress, rides)

    def _fewer_trains(self, rides: tuple[Ride, ...], start: dt.datetime, access: dict[str, Edge]) -> tuple[Ride, ...]:
        """Equal arrivals keep the first trains the scan found, often a hop to where the express
        also stops: board the latest ride's train at one of the city's own stations instead,
        when the road there still leaves after start (the latest such leave wins)."""
        for k in range(len(rides) - 1, 0, -1):
            r = rides[k]
            stops = self.timetable.trains[r.train]["stops"]
            at = {st["code"]: n for n, st in enumerate(stops)}
            board = at.get(r.board)
            best: tuple[dt.datetime, Ride] | None = None
            for code, e in access.items():
                n = at.get(code)
                if n is None or board is None or n >= board:
                    continue
                dep = r.depart - timedelta(minutes=_run_min(stops[board]) - _run_min(stops[n]))
                leave = dep - timedelta(minutes=BOARD_MIN + round(e.minutes))
                if leave >= start and (best is None or leave > best[0]):
                    a, b = self.timetable.stations[code], self.timetable.stations[r.alight]
                    km = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) * RAIL_DETOUR
                    best = (leave, replace(r, board=code, depart=dep, km=km))
            if best is not None:
                return (best[1], *rides[k + 1:])
        return rides

    def _leave(self, j: Journey, access: dict[str, Edge]) -> dt.datetime:
        return j.rides[0].depart - timedelta(minutes=BOARD_MIN + round(access[j.access].minutes))

    def _arrive(self, j: Journey, egress: dict[str, Edge]) -> dt.datetime:
        return j.rides[-1].arrive + timedelta(minutes=round(egress[j.egress].minutes))

    def _rail_journey(self, src: Node, dst: Node, start: dt.datetime,
                      access: dict[str, Edge], egress: dict[str, Edge]) -> Journey | None:
        """The earliest arrival, then the latest departure that still arrives as early:
        no early start to wait at a station or ride a detour onto the same train."""
        j = self._scan(start, access, egress)
        for _ in range(12):
            if j is None:
                return None
            later = self._scan(self._leave(j, access) + timedelta(minutes=1), access, egress)
            if later is None or self._arrive(later, egress) > self._arrive(j, egress):
                return j
            j = later
        return j

    def train_class(self, train: str, style: str | None = None) -> str:
        """The class a party of this budget style rides on the train (fares.rail_class)."""
        return pick_class(self.timetable.classes(train), style)

    def _rail_option(self, j: Journey, src: Node, dst: Node, travellers: int,
                     access: dict[str, Edge], egress: dict[str, Edge], style: str | None = None) -> Found:
        """Legs with real train times: leave in time for the first train (BOARD_MIN at the
        station), wait between trains, then the transfer on from the last station."""
        first, last = access[j.access], egress[j.egress]
        a_min, e_min = round(first.minutes), round(last.minutes)
        leave = self._leave(j, access)
        legs = [Leg(**{"from": src.name}, to=self._station(j.access).name, mode=Mode.road, depart=leave,
                    arrive=leave + timedelta(minutes=a_min), minutes=a_min,
                    cost_inr=round(_party_cost(first, travellers).cost_inr))]
        legs += [Leg(**{"from": self._station(r.board).name}, to=self._station(r.alight).name, mode=Mode.rail,
                     depart=r.depart, arrive=r.arrive, minutes=r.minutes,
                     cost_inr=rail_fare(r.km, self.train_class(r.train, style)) * travellers,
                     ref=r.train)
                 for r in j.rides]
        end = j.rides[-1].arrive
        legs.append(Leg(**{"from": self._station(j.egress).name}, to=dst.name, mode=Mode.road, depart=end,
                        arrive=end + timedelta(minutes=e_min), minutes=e_min,
                        cost_inr=round(_party_cost(last, travellers).cost_inr)))
        ride_min = sum(r.minutes for r in j.rides)
        comfort = (COMFORT["rail"] * ride_min + first.comfort * a_min + last.comfort * e_min) / max(1, ride_min + a_min + e_min)
        opt = TransportOption(mode=Mode.rail, legs=legs, total_minutes=round((legs[-1].arrive - leave).total_seconds() / 60),
                              total_cost_inr=sum(leg.cost_inr for leg in legs), comfort=min(5, max(1, round(comfort * 5))))
        vehicles = len(j.rides) + sum(e.mode != "walk" for e in (first, last))
        sources = sorted({self.rail_source} | {_source(e, {}) for e in (first, last)})
        return Found(Mode.rail, opt, max(0, vehicles - 1), sources)

    def _rail(self, src: Node, dst: Node, start: dt.datetime, travellers: int,
              style: str | None = None) -> Found | None:
        """Of the day's sensible journeys from start, the one arriving first once each change
        between trains counts as RAIL_CHANGE_MIN later and the cab on from the last station
        counts EGRESS_WEIGHT times."""
        stop = dt.datetime.combine(start.date(), dt.time(23, 59))
        found = sensible(self._rail_found(src, dst, start, stop, travellers, RAIL_CANDIDATES, style))

        def late(f: Found) -> dt.datetime:
            legs = f.option.legs
            cab = legs[-1].minutes if legs[-1].mode is Mode.road else 0
            return legs[-1].arrive + timedelta(minutes=RAIL_CHANGE_MIN * (_trains(f.option) - 1) + (EGRESS_WEIGHT - 1) * cab)

        return min(found, key=late, default=None)

    def _rail_found(self, src: Node, dst: Node, start: dt.datetime, stop: dt.datetime,
                    travellers: int, limit: int, style: str | None = None) -> list[Found]:
        access, egress = self._ends(src, True), self._ends(dst, False)
        out: list[Found] = []
        while len(out) < limit and start <= stop:
            j = self._rail_journey(src, dst, start, access, egress)
            if j is None:
                break
            f = self._rail_option(j, src, dst, travellers, access, egress, style)
            opt = f.option
            if opt.legs[0].depart > stop:
                break
            last = out[-1].option if out else None
            if last is None or opt.legs[-1].arrive < last.legs[-1].arrive or opt.legs[0].depart > last.legs[0].depart:
                out.append(f)
            start = max(start, opt.legs[0].depart) + timedelta(minutes=1)  # always move on
        return out

    def rail_departures(self, origin: str, destination: str, day: dt.date, earliest: dt.time = dt.time(5, 0),
                        latest: dt.time = dt.time(23, 59), travellers: int = 1, limit: int = 6,
                        rail_class: str | None = None) -> list[TransportOption]:
        """Sensible rail journeys (see `sensible`) leaving origin between earliest and latest
        on day, from the real timetable, in order of departure, priced for the whole party
        in the class rail_class ("budget" | "mid" | "luxury", fares.STYLE_CLASSES) rides. legs[0].depart is when to leave
        the city centre (in time for the first train); legs[-1].arrive is arrival in the destination."""
        src, dst = resolve_city(origin), resolve_city(destination)
        start, stop = dt.datetime.combine(day, earliest), dt.datetime.combine(day, latest)
        return [f.option for f in sensible(self._rail_found(src, dst, start, stop, travellers, limit, rail_class))]

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
                if a.id == b.id or self._too_close(a, b):
                    continue  # no live call for a pair nobody flies
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
        if res is None or sum(e.mode == "air" for e in res.edges) > 1:
            return None  # one flight only: estimated connections are not offered (live ones never are)
        # one leg per vehicle, built by the same code as search
        merged = tuple(_party_cost(e, travellers) for e in _merge(res.edges))
        opt = _result(merged, res.objective, res.expansions, start).option
        # ref: the flight number of a live flight (estimated flights have none)
        legs = [leg.model_copy(update={"from_": _label(g.nodes[e.src]), "to": _label(g.nodes[e.dst]),
                                       "ref": e.ref if e.mode == "air" and e.ref in live else None})
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

    def _too_close(self, a: Node, b: Node) -> bool:
        return haversine_km(a.lat, a.lon, b.lat, b.lon) < MIN_FLIGHT_KM

    def _why_not(self, g: Graph, src: Node, dst: Node, mode: Mode) -> str:
        if mode is Mode.air:
            near = {}
            for p in (src, dst):
                near[p.id] = self._near_airports(g, p)
                if not near[p.id]:
                    return f"no airport within {AIRPORT_KM} km of {p.name}"
            if all(self._too_close(a, b) for a in near[src.id] for b in near[dst.id]):
                return f"{src.name} and {dst.name} are too close to fly between"
            return f"no flight between the airports near {src.name} and {dst.name}"
        if mode is Mode.rail:
            if not self._ends(src, True) or not self._ends(dst, False):
                p = src if not self._ends(src, True) else dst
                return f"no railway station within {STATION_KM} km of {p.name}"
            return f"no train in the timetable links {src.name} and {dst.name} within 48 hours"
        return f"no road route found between {src.name} and {dst.name}"

    def compare(self, req: CompareRequest, rail_class: str | None = None) -> CompareResponse:
        """rail_class: the budget style rail is priced for ("budget" | "mid" | "luxury"; None is mid)."""
        src, dst = resolve_city(req.origin), resolve_city(req.destination)
        if src.id == dst.id:
            raise UnknownPlace("origin and destination are the same place")
        day = req.date or dt.date.today()
        start = dt.datetime.combine(day, req.depart_time)
        g = self._graph_for([src, dst])
        live = self._live_air(g, src, dst, day, start) if Mode.air in req.modes else {}
        found, unavailable = [], []
        for mode in sorted(set(req.modes), key=MODE_ORDER.get):
            if mode is Mode.rail:
                f = self._rail(src, dst, start, req.travellers, rail_class)
            else:
                f = self._find(g, src, dst, mode, start, req.travellers, live)
                if f and mode is Mode.road and f.option.total_minutes > MAX_DRIVE_MIN:
                    unavailable.append(Unavailable(mode=mode, reason=f"{src.name} to {dst.name} is a drive of over "
                                                   f"{MAX_DRIVE_MIN // 60} hours; go by rail or air"))
                    continue
            if f:
                found.append(f)
            else:
                unavailable.append(Unavailable(mode=mode, reason=self._why_not(g, src, dst, mode)))
        return CompareResponse(
            origin=CityRef(name=src.name, lat=src.lat, lng=src.lon),
            destination=CityRef(name=dst.name, lat=dst.lat, lng=dst.lon),
            date=day, rank_by=req.rank_by, options=rank(found, req.rank_by, req.travellers), unavailable=unavailable,
            notes=[_rail_note(self.rail_source), _road_note(), _air_note(found)],
        )


def _run_min(stop: dict) -> int:
    """A stop's departure in minutes from midnight of the train's first day."""
    return (stop["day"] - 1) * 1440 + (stop["dep"] if stop["dep"] is not None else stop["arr"])


def _rail_note(source: str) -> str:
    if source == "sample_rail":
        return "Rail uses the fictional sample timetable (fallback)."
    return ("Rail uses real timetables from datameet (about 2016; every train treated as daily): check the "
            "train on IRCTC before booking. Fares are estimates for the class shown on the IRCTC card.")


def _road_note() -> str:
    return (f"By car: fuel (about Rs {FUEL_INR_PER_KM:g} a km) and tolls on known expressways, per car of four. "
            "Rides to and from stations and airports are cab fares, per cab of four.")


def _air_note(found: list[Found]) -> str:
    if any("serpapi_flights" in f.sources for f in found):
        return ("Air uses Google Flights fares (economy, via SerpApi, cached up to 6 hours) for the reachable "
                f"flight best on arrival time and fare; the flight leg includes {AIRPORT_MIN} min at the airport.")
    return "Air uses estimated fares and times; seller links search the same route and date."


def _trains(opt: TransportOption) -> int:
    return sum(leg.mode is Mode.rail for leg in opt.legs)


def at_night(opt: TransportOption) -> bool:
    """Leaves the city, arrives, or changes trains between midnight and 05:00 (riding a
    sleeper through the night is fine)."""
    rails = [leg for leg in opt.legs if leg.mode is Mode.rail]
    times = [opt.legs[0].depart, opt.legs[-1].arrive]
    times += [t for a, b in zip(rails, rails[1:], strict=False) for t in (a.arrive, b.depart)]
    return any(t.hour < NIGHT_END_HOUR for t in times)


def _beats(p: TransportOption, o: TransportOption) -> bool:
    """p leaves no earlier, arrives no later and takes no more trains than o."""
    return (p.legs[0].depart >= o.legs[0].depart and p.legs[-1].arrive <= o.legs[-1].arrive
            and _trains(p) <= _trains(o))


def sensible(found: list[Found]) -> list[Found]:
    """Rail journeys worth offering, in their order: none that is `at_night` while another
    is not (a night arrival or change needs that strong reason: nothing else), and none
    that another journey beats (the first of equals stays)."""
    day = [f for f in found if not at_night(f.option)] or list(found)
    return [f for i, f in enumerate(day)
            if not any(_beats(g.option, f.option) and (j < i or not _beats(f.option, g.option))
                       for j, g in enumerate(day) if j != i)]


def is_overnight(opt: TransportOption) -> bool:
    """A train ride that runs past midnight, or before 05:00."""
    return any(leg.mode is Mode.rail and (leg.arrive.date() > leg.depart.date() or leg.depart.hour < NIGHT_END_HOUR
                                          or leg.arrive.hour < NIGHT_END_HOUR)
               for leg in opt.legs)


def _overnight_penalised(f: Found, found: list[Found], travellers: int) -> bool:
    """An overnight train is pushed down when a daytime option exists and either the trip
    is short (that option takes at most SHORT_TRIP_MIN) or one person travels alone. When
    every option is overnight, or the night train is the only one, it keeps its place."""
    if not is_overnight(f.option):
        return False
    day = [g for g in found if not is_overnight(g.option)]
    return bool(day) and (travellers == 1 or min(g.option.total_minutes for g in day) <= SHORT_TRIP_MIN)


def rank(found: list[Found], rank_by: RankBy, travellers: int = 1) -> list[RankedOption]:
    if not found:
        return []
    best_t = min(f.option.total_minutes for f in found) or 1
    best_c = min(f.option.total_cost_inr for f in found) or 1

    def score(f: Found) -> float:
        night = OVERNIGHT_PENALTY if _overnight_penalised(f, found, travellers) else 0.0
        return f.option.total_minutes / best_t + f.option.total_cost_inr / best_c + CHANGE_WEIGHT * f.changes + night

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
