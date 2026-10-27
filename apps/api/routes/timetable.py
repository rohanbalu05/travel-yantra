"""Rail journeys on real timetables: earliest arrival by connection scan (CSA)
over every train's stop-to-stop connections, with changes between trains.

The timetable is the datameet corridor subset (see data/rail_meta.json), or
the sample when ROUTES_RAIL=sample. Datameet has no running days, so every
train is treated as daily (a reversible assumption). Times are minutes from
00:00 of the travel day; a train that left its origin a day or two earlier
still counts if it passes the station after the start time."""
from __future__ import annotations

import bisect
import datetime as dt
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .graph import RAIL_DETOUR, RAIL_INR_PER_KM, _read_json, haversine_km, rail_dir

CHANGE_MIN = 15  # between two trains at the same station
BOARD_MIN = 15  # at the station before the first train
HORIZON_MIN = 30 * 60  # search window from the start time
EARLIER_RUNS = 3  # runs that left their origin up to this many days before the travel day


@dataclass(frozen=True)
class Conn:
    dep: int  # minutes after the run's day-0 midnight
    arr: int
    a: str
    b: str
    train: str


@dataclass(frozen=True)
class Ride:
    train: str
    name: str
    board: str  # station code
    alight: str
    depart: dt.datetime
    arrive: dt.datetime
    km: float

    @property
    def minutes(self) -> int:
        return round((self.arrive - self.depart).total_seconds() / 60)

    @property
    def fare_inr(self) -> float:  # per person, an estimate (no fare table in the source)
        return self.km * RAIL_INR_PER_KM


@dataclass(frozen=True)
class Journey:
    access: str  # first station
    egress: str  # last station
    rides: tuple[Ride, ...]


class Timetable:
    def __init__(self, data_dir: Path) -> None:
        self.stations = {s["code"]: s for s in _read_json("rail_stations", data_dir)}
        self.trains = {t["number"]: t for t in _read_json("rail_trains", data_dir)}
        conns = []
        for t in self.trains.values():
            stops = t["stops"]
            for a, b in zip(stops, stops[1:], strict=False):
                dep = a["dep"] if a["dep"] is not None else a["arr"]
                arr = b["arr"] if b["arr"] is not None else b["dep"]
                if dep is None or arr is None:
                    continue
                d, r = (a["day"] - 1) * 1440 + dep, (b["day"] - 1) * 1440 + arr
                if r > d and a["code"] in self.stations and b["code"] in self.stations:
                    conns.append(Conn(d, r, a["code"], b["code"], t["number"]))
        self.conns = sorted(conns, key=lambda c: c.dep)
        self._deps = [c.dep for c in self.conns]
        served: dict[str, int] = {}
        for t in self.trains.values():
            for s in {s["code"] for s in t["stops"]}:
                served[s] = served.get(s, 0) + 1
        self.served = served  # trains stopping at each station

    def _window(self, t0: int, horizon: int) -> list[tuple[int, int, Conn, int]]:
        """(dep, arr, conn, run) for every daily run, as minutes from the travel day's
        midnight, departing in [t0, t0 + horizon], sorted by departure."""
        out = []
        for run in range(-EARLIER_RUNS, 2):  # run = days between the run's day 0 and the travel day
            shift = run * 1440
            i = bisect.bisect_left(self._deps, t0 - shift)
            j = bisect.bisect_right(self._deps, t0 + horizon - shift)
            out += [(c.dep + shift, c.arr + shift, c, run) for c in self.conns[i:j]]
        out.sort(key=lambda x: (x[0], x[1]))
        return out

    def earliest(self, access: dict[str, int], egress: dict[str, int], t0: int,
                 horizon: int = HORIZON_MIN) -> tuple[list[tuple[int, int, Conn]], int] | None:
        """Connection scan. access: station -> minute you can board there (from the
        travel day's midnight); egress: station -> minutes on to the destination.
        Returns the rides as (board index, alight index, ...) resolved to
        [(dep, arr, conn) per ride], and the arrival at the destination."""
        conns = self._window(t0, horizon)
        reach = dict(access)  # station -> earliest time you can board a train there
        boarded: dict[tuple[str, int], int] = {}  # (train, run) -> index of the boarding connection
        came: dict[str, tuple[int, int]] = {}  # station -> (board index, alight index)
        best, best_at = None, None
        for i, (dep, arr, c, run) in enumerate(conns):
            if best is not None and dep >= best:
                break
            trip = (c.train, run)
            if trip not in boarded:
                if reach.get(c.a, 1 << 30) > dep:
                    continue
                boarded[trip] = i
            if arr + CHANGE_MIN < reach.get(c.b, 1 << 30):
                reach[c.b] = arr + CHANGE_MIN
                came[c.b] = (boarded[trip], i)
            if c.b in egress and (best is None or arr + egress[c.b] < best):
                best, best_at = arr + egress[c.b], (c.b, boarded[trip], i)
        if best_at is None:
            return None
        rides = []
        station, b_i, a_i = best_at
        while True:
            rides.append((conns[b_i], conns[a_i]))
            station = conns[b_i][2].a
            if station in access and (station not in came or came[station][1] >= b_i):
                break
            b_i, a_i = came[station]
        rides.reverse()
        return [(b[0], a[1], b[2], a[2]) for b, a in rides], best

    def journey(self, access: dict[str, int], egress: dict[str, int], day: dt.date, start: dt.time,
                horizon: int = HORIZON_MIN) -> Journey | None:
        midnight = dt.datetime.combine(day, dt.time())
        t0 = start.hour * 60 + start.minute
        found = self.earliest(access, egress, t0, horizon)
        if found is None:
            return None
        rides = []
        for dep, arr, first, last in found[0]:
            a, b = self.stations[first.a], self.stations[last.b]
            km = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) * RAIL_DETOUR
            rides.append(Ride(first.train, self.trains[first.train]["name"], first.a, last.b,
                              midnight + dt.timedelta(minutes=dep), midnight + dt.timedelta(minutes=arr), km))
        return Journey(rides[0].board, rides[-1].alight, tuple(rides))

    def near(self, lat: float, lon: float, max_km: float, k: int, min_served: int = 3,
             hub_km: float = 15.0) -> list[tuple[str, float]]:
        """Stations for a city: the k nearest within max_km served by at least
        min_served trains, plus the k busiest within hub_km (a big city's main
        stations are not always its nearest). Nearest first, no repeats."""
        hits = []
        for code, s in self.stations.items():
            if self.served.get(code, 0) < min_served:
                continue
            km = haversine_km(lat, lon, s["lat"], s["lon"])
            if km <= max_km:
                hits.append((km, code))
        hits.sort()
        busiest = sorted((h for h in hits if h[0] <= hub_km), key=lambda h: -self.served[h[1]])[:k]
        return [(c, km) for km, c in sorted(set(hits[:k]) | set(busiest))]


@lru_cache(maxsize=2)
def _load(data_dir: Path) -> Timetable:
    return Timetable(data_dir)


def get_timetable(data_dir: Path | None = None) -> Timetable:
    return _load(data_dir or rail_dir())
