"""IRCTC copy card and PNR timeline mock. There is no IRCTC API and we never
scrape it: the card is everything IRCTC's form asks for, in its order, for the
traveller to paste; the PNR timeline replays sample data only."""
from __future__ import annotations

import datetime as dt
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .graph import (
    DATA_DIR,
    RAIL_DETOUR,
    RAIL_INR_PER_KM,
    SAMPLE_RAIL_DIR,
    _read_json,
    haversine_km,
    rail_dir,
)

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
BOOKING_URL = "https://www.irctc.co.in/nget/train-search"
TravelClass = Literal["SL", "3E", "3A", "2A", "1A", "CC", "2S"]
# Fare multiplier on the sleeper estimate (reversible assumption, not IRCTC's fare table).
CLASS_FARE = {"2S": 0.6, "SL": 1.0, "CC": 2.1, "3E": 2.4, "3A": 2.6, "2A": 3.7, "1A": 6.2}
SEAT_CLASSES = {"CC", "2S"}
LOWER_BERTH_AGE = 45

# Sample personas only (packages/contracts/samples); never real travellers.
PARTIES: dict[str, list[tuple[str, int, str]]] = {
    "goa_family": [("Arjun Rao", 34, "Male"), ("Venkatesh", 64, "Male"),
                   ("Shobha", 58, "Female"), ("Meera", 22, "Female")],
    "mysuru_weekend": [("Arjun Rao", 34, "Male"), ("Meera", 22, "Female")],
}
Party = Literal["goa_family", "mysuru_weekend"]


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


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _find_run(src: str, dst: str, train: str | None, data_dir: Path | None) -> tuple[dict, dict, dict]:
    _, trains = _rail(data_dir)
    for t in trains:
        if train and t["number"] != train:
            continue
        codes = [s["code"] for s in t["stops"]]
        if src in codes and dst in codes and codes.index(src) < codes.index(dst):
            return t, t["stops"][codes.index(src)], t["stops"][codes.index(dst)]
    which = f"train {train}" if train else "no sample train"
    raise NotFound(f"{which} does not run from {src} to {dst}")


def _berths(party: list[tuple[str, int, str]], cls: str) -> list[str]:
    if cls in SEAT_CLASSES:
        return ["No preference"] * len(party)
    rest = iter(["Upper", "Middle", "Side Lower", "Side Upper"] * len(party))
    return ["Lower" if age >= LOWER_BERTH_AGE else next(rest) for _, age, _ in party]


def irctc_card(src: str, dst: str, date: dt.date, travel_class: TravelClass = "3A",
               party: Party = "goa_family", train: str | None = None,
               data_dir: Path | None = None) -> IrctcCard:
    a, b = resolve_station(src, data_dir), resolve_station(dst, data_dir)
    t, dep, arr = _find_run(a["code"], b["code"], train, data_dir)
    dep_min = dep["dep"] if dep["dep"] is not None else dep["arr"]
    arr_min = arr["arr"] if arr["arr"] is not None else arr["dep"]
    people = PARTIES[party]
    passengers = [Passenger(name=n, age=age, gender=g, berth=berth)
                  for (n, age, g), berth in zip(people, _berths(people, travel_class), strict=True)]
    km = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) * RAIL_DETOUR
    fare = math.ceil(km * RAIL_INR_PER_KM * CLASS_FARE[travel_class]) * len(people)
    date_irctc = date.strftime("%d-%m-%Y")
    lines = [f"From: {a['code']} ({a['name']})", f"To: {b['code']} ({b['name']})", f"Date: {date_irctc}",
             f"Class: {travel_class}", "Quota: General",
             f"Train: {t['number']} {t['name']}, departs {_hhmm(dep_min)}", "Passengers:"]
    lines += [f"{i}. {p.name}, {p.age}, {p.gender}, {p.berth}" for i, p in enumerate(passengers, 1)]
    return IrctcCard(
        train=TrainRef(number=t["number"], name=t["name"]),
        from_=StationRef(code=a["code"], name=a["name"]), to=StationRef(code=b["code"], name=b["name"]),
        date=date, date_irctc=date_irctc, departs=_hhmm(dep_min), arrives=_hhmm(arr_min),
        arrives_day_offset=arr["day"] - dep["day"], travel_class=travel_class, passengers=passengers,
        fare_estimate_inr=fare, copy_text="\n".join(lines),
        notes=[("Sample timetable" if (data_dir or rail_dir()) == SAMPLE_RAIL_DIR
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
    stations, trains = _rail(SAMPLE_RAIL_DIR)  # sample PNRs name the sample trains
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
