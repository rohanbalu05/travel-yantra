"""IRCTC copy card and PNR timeline mock. There is no IRCTC API and we never
scrape it: the card is everything IRCTC's form asks for, in its order, for the
traveller to paste; the PNR timeline replays sample data only."""
from __future__ import annotations

import datetime as dt
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .fares import rail_class, rail_fare
from .graph import (
    DATA_DIR,
    RAIL_DETOUR,
    ROAD_DETOUR,
    ROAD_KMH,
    SAMPLE_RAIL_DIR,
    _read_json,
    haversine_km,
    rail_dir,
)

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
BOOKING_URL = "https://www.irctc.co.in/nget/train-search"
TravelClass = Literal["SL", "3E", "3A", "2A", "1A", "CC", "EC", "2S"]
Style = Literal["budget", "mid", "luxury"]
SEAT_CLASSES = {"CC", "EC", "2S"}
DEFAULT_AFTER = dt.time(6, 0)  # with no train named, the first that leaves at or after this
LOWER_BERTH_AGE = 45

# Sample personas only (packages/contracts/samples); never real travellers.
PARTIES: dict[str, list[tuple[str, int, str]]] = {
    "goa_family": [("Arjun Rao", 34, "Male"), ("Venkatesh", 64, "Male"),
                   ("Shobha", 58, "Female"), ("Meera", 22, "Female")],
    "mysuru_weekend": [("Arjun Rao", 34, "Male"), ("Meera", 22, "Female")],
}
Party = Literal["goa_family", "mysuru_weekend"]
MAX_TRAVELLERS = 6  # IRCTC books up to six passengers on one ticket


def _people(party: Party, travellers: int | None) -> list[tuple[str, int, str]]:
    """The sample party, made up to the trip's traveller count: the party first, then the
    other sample personas, then numbered sample travellers."""
    base = PARTIES[party]
    if travellers is None:
        return base
    pool = base + [p for ps in PARTIES.values() for p in ps if p not in base]
    pool = list(dict.fromkeys(pool))
    pool += [(f"Traveller {i}", 30, "Female" if i % 2 else "Male") for i in range(len(pool) + 1, MAX_TRAVELLERS + 1)]
    return pool[:travellers]


class NotFound(LookupError):
    pass


class StationRef(BaseModel):
    code: str
    name: str


class TrainRef(BaseModel):
    number: str
    name: str


class Passenger(BaseModel):
    name: str
    age: int
    gender: str
    berth: str


class IrctcCard(BaseModel):
    train: TrainRef
    from_: StationRef = Field(serialization_alias="from")
    to: StationRef
    date: dt.date
    date_irctc: str  # DD-MM-YYYY, as IRCTC's form wants it
    departs: str
    arrives: str
    arrives_day_offset: int
    travel_class: TravelClass
    classes: list[TravelClass] = Field(default_factory=list)  # every class this train carries
    quota: str = "General"
    passengers: list[Passenger]
    fare_estimate_inr: int  # whole party
    copy_text: str
    booking_url: str = BOOKING_URL
    sample: bool = True
    notes: list[str] = Field(default_factory=list)


class PnrPassenger(BaseModel):
    name: str
    status: str


class PnrEvent(BaseModel):
    at: dt.datetime
    status: str
    note: str


class PnrStatus(BaseModel):
    pnr: str
    train: str
    class_: str = Field(serialization_alias="class")
    date: dt.date
    from_: StationRef = Field(serialization_alias="from")
    to: StationRef
    passengers: list[PnrPassenger]
    timeline: list[PnrEvent]
    current_status: str
    chart_prepared: bool
    sample: bool = True


def _rail(data_dir: Path | None = None) -> tuple[dict[str, dict], list[dict]]:
    return _rail_at(data_dir or rail_dir())


@lru_cache(maxsize=4)
def _rail_at(data_dir: Path) -> tuple[dict[str, dict], list[dict]]:
    stations = {s["code"]: s for s in _read_json("rail_stations", data_dir)}
    return stations, _read_json("rail_trains", data_dir)


def resolve_station(value: str, data_dir: Path | None = None) -> dict:
    stations, _ = _rail(data_dir)
    v = value.strip()
    if v.upper() in stations:
        return stations[v.upper()]
    for s in stations.values():
        if s["name"].lower() == v.lower():
            return s
    raise NotFound(f"unknown station {value!r}")


def _station_for(value: str, train: str | None, data_dir: Path | None, board: bool) -> dict:
    """A station by code or name; or, for a city name (as on a plan's journey leg) and a
    train number, the stop the planner uses among compare's stations for the city:
    boarding, the one you can leave the city latest for (departure less the drive there);
    getting off, the one nearest the city."""
    try:
        return resolve_station(value, data_dir)
    except NotFound:
        if not train:
            raise
    from .compare import (  # compare imports the timetable
        STATION_K,
        STATION_KM,
        UnknownPlace,
        resolve_city,
    )
    from .timetable import get_timetable

    try:
        city = resolve_city(value)
    except UnknownPlace as exc:
        raise NotFound(f"unknown station or city {value!r}") from exc
    stations, trains = _rail(data_dir)
    t = next((t for t in trains if t["number"] == train), None)
    served = dict(get_timetable(data_dir).near(city.lat, city.lon, STATION_KM, STATION_K))  # compare's stations
    near = [(s, km) for s in (t["stops"] if t else []) if (km := served.get(s["code"])) is not None]
    if not near:
        raise NotFound(f"train {train} does not stop near {city.name}")
    if not board:
        return stations[min(near, key=lambda n: n[1])[0]["code"]]

    def leave(n: tuple[dict, float]) -> float:  # minutes from the run's day 1 midnight
        s, km = n
        dep = s["dep"] if s["dep"] is not None else s["arr"]
        return (s["day"] - 1) * 1440 + (dep or 0) - km * ROAD_DETOUR / ROAD_KMH * 60

    return stations[max(near, key=leave)[0]["code"]]


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _dep(stop: dict) -> int:
    return stop["dep"] if stop["dep"] is not None else stop["arr"]


def _find_run(src: str, dst: str, train: str | None, data_dir: Path | None,
              after: dt.time | None = None) -> tuple[dict, dict, dict]:
    """The named train; else, of the trains running src to dst, the first leaving at or after
    `after` (DEFAULT_AFTER), or the day's first when none leaves that late."""
    _, trains = _rail(data_dir)
    runs = []
    for t in trains:
        if train and t["number"] != train:
            continue
        codes = [s["code"] for s in t["stops"]]
        if src in codes and dst in codes and codes.index(src) < codes.index(dst):
            runs.append((t, t["stops"][codes.index(src)], t["stops"][codes.index(dst)]))
    if not runs:
        which = f"train {train}" if train else "no train"
        raise NotFound(f"{which} does not run from {src} to {dst}")
    at = (after or DEFAULT_AFTER).hour * 60 + (after or DEFAULT_AFTER).minute
    runs.sort(key=lambda r: (_dep(r[1]) % 1440, r[0]["number"]))
    return next((r for r in runs if _dep(r[1]) % 1440 >= at), runs[0])


def train_classes(train: dict) -> list[str]:
    """The classes a train carries (build_rail.classes); the sample trains list none."""
    from .timetable import SAMPLE_CLASSES

    return train.get("classes") or list(SAMPLE_CLASSES)


def _berths(party: list[tuple[str, int, str]], cls: str) -> list[str]:
    if cls in SEAT_CLASSES:
        return ["No preference"] * len(party)
    rest = iter(["Upper", "Middle", "Side Lower", "Side Upper"] * len(party))
    return ["Lower" if age >= LOWER_BERTH_AGE else next(rest) for _, age, _ in party]


def irctc_card(src: str, dst: str, date: dt.date, travel_class: TravelClass | None = None,
               party: Party = "goa_family", train: str | None = None,
               data_dir: Path | None = None, travellers: int | None = None,
               after: dt.time | None = None, style: Style | None = None) -> IrctcCard:
    """travellers: the trip's party size (the sample party is made up or cut to it).
    travel_class: when it is omitted or the train does not carry it, the class compare prices
    this train in for the budget style (fares.rail_class; style None is "mid"), so the card's
    fare is the plan's fare. after: with no train named, the first train leaving from then."""
    a, b = _station_for(src, train, data_dir, board=True), _station_for(dst, train, data_dir, board=False)
    t, dep, arr = _find_run(a["code"], b["code"], train, data_dir, after)
    classes = train_classes(t)
    notes = []
    if travel_class not in classes:
        chosen = rail_class(classes, style)
        if travel_class is not None:
            notes.append(f"{t['number']} has no {travel_class}; showing {chosen} (it carries {', '.join(classes)}).")
        travel_class = chosen
    dep_min = _dep(dep)
    arr_min = arr["arr"] if arr["arr"] is not None else arr["dep"]
    people = _people(party, travellers)
    passengers = [Passenger(name=n, age=age, gender=g, berth=berth)
                  for (n, age, g), berth in zip(people, _berths(people, travel_class), strict=True)]
    km = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) * RAIL_DETOUR  # as timetable.Ride.km
    fare = rail_fare(km, travel_class) * len(people)
    date_irctc = date.strftime("%d-%m-%Y")
    lines = [f"From: {a['code']} ({a['name']})", f"To: {b['code']} ({b['name']})", f"Date: {date_irctc}",
             f"Class: {travel_class}", "Quota: General",
             f"Train: {t['number']} {t['name']}, departs {_hhmm(dep_min)}", "Passengers:"]
    lines += [f"{i}. {p.name}, {p.age}, {p.gender}, {p.berth}" for i, p in enumerate(passengers, 1)]
    return IrctcCard(
        train=TrainRef(number=t["number"], name=t["name"]),
        from_=StationRef(code=a["code"], name=a["name"]), to=StationRef(code=b["code"], name=b["name"]),
        date=date, date_irctc=date_irctc, departs=_hhmm(dep_min), arrives=_hhmm(arr_min),
        arrives_day_offset=arr["day"] - dep["day"], travel_class=travel_class,
        classes=classes, passengers=passengers,
        fare_estimate_inr=fare, copy_text="\n".join(lines),
        notes=notes + [("Sample timetable" if (data_dir or rail_dir()) == SAMPLE_RAIL_DIR
                else "Timetable from datameet (about 2016): check the train runs that day on IRCTC")
               + "; sample travellers.",
               "Fare is an estimate; IRCTC shows the real fare when you book."],
    )


@lru_cache(maxsize=4)
def _pnrs(data_dir: Path = DATA_DIR) -> dict[str, dict]:
    rows = json.loads((data_dir / "sample_pnrs.json").read_text(encoding="utf-8"))
    return {r["pnr"]: r for r in rows}


def pnr_status(pnr: str, at: dt.datetime | None = None, data_dir: Path = DATA_DIR) -> PnrStatus:
    row = _pnrs(data_dir).get(pnr)
    if row is None:
        raise NotFound("unknown sample PNR")
    at = at or dt.datetime.now(IST)
    if at.tzinfo is None:
        at = at.replace(tzinfo=IST)
    events = [e for e in row["events"] if dt.datetime.fromisoformat(e["at"]) <= at]
    current = events[-1]["status"] if events else "NOT BOOKED YET"
    people = PARTIES[row["party"]]
    if current == "CNF":
        statuses = [f"CNF {berth}" for berth in row["berths"]]
    else:
        statuses = [current] * len(people)
    stations, trains = _rail_at(DATA_DIR)  # sample PNRs and people on real datameet trains
    train_name = next((t["name"] for t in trains if t["number"] == row["train"]), "")
    a, b = stations[row["from"]], stations[row["to"]]
    return PnrStatus(
        pnr=pnr, train=f"{row['train']} {train_name}".strip(), class_=row["class"],
        date=dt.date.fromisoformat(row["date"]),
        from_=StationRef(code=a["code"], name=a["name"]), to=StationRef(code=b["code"], name=b["name"]),
        passengers=[PnrPassenger(name=n, status=s) for (n, _, _), s in zip(people, statuses, strict=True)],
        timeline=[PnrEvent(at=e["at"], status=e["status"], note=e["note"]) for e in events],
        current_status=current, chart_prepared=any(e.get("chart") for e in events),
    )
