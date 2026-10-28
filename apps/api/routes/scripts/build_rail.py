"""Build the processed rail subset from datameet/railways (CC0) raw files.

Usage:
    python build_rail.py --src <dir with stations.json trains.json schedules.json> \
        --out apps/api/routes/data [--bbox demo | --bbox minlat,minlon,maxlat,maxlon] [--cities]

Keeps stations in Karnataka, Goa, Maharashtra, Kerala, Tamil Nadu and Andhra
Pradesh, or with --bbox the stations inside a box whatever their state (many
datameet stations have no state, Yesvantpur and Chikkamagaluru among them),
and trains that stop at two or more of them. With --cities, also every station
within CITY_KM of a city in data/cities.json, for long-distance trains only
(suburban and unlisted trains keep their stops inside the box). Each train
keeps its type and the classes it carries (from datameet's class flags). Words in capitals in station and
train names are title-cased. Writes rail_meta.json (source, licence, filter, counts). Output
files are gzipped when larger than 5 MB.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
from pathlib import Path

STATES = {"karnataka", "goa", "maharashtra", "kerala", "tamil nadu", "andhra pradesh"}
# The demo corridors: Bengaluru, Mysuru and the Coorg side, Hassan, Chikkamagaluru,
# Hosapete for Hampi, Hubballi, and Goa.
DEMO_BBOX = (11.5, 73.6, 16.0, 78.0)
SOURCE = "https://github.com/datameet/railways (stations.json, trains.json, schedules.json)"
LICENCE = "CC0 1.0 (public domain dedication)"
GZIP_OVER = 5 * 1024 * 1024
CITY_KM = 40  # compare looks for stations this far from a city (compare.STATION_KM)
CITIES = Path(__file__).resolve().parents[1] / "data" / "cities.json"
LOCAL_TYPES = {"MEMU", "DEMU", "EMU", "Toy", ""}  # outside the box, only long-distance trains are kept
SEAT_TYPES = {"Shtb", "JShtb"}  # chair-car day trains: a first_ac flag means Executive Chair (EC)


def classes(props: dict) -> list[str]:
    """The classes a train carries, from datameet's flags; a train with none is unreserved (2S).
    No flags at all (the hand-made sample): [] (timetable.SAMPLE_CLASSES applies)."""
    keys = ("first_ac", "second_ac", "third_ac", "chair_car", "sleeper")
    if all(props.get(k) is None for k in keys):
        return []
    if props.get("type") in SEAT_TYPES:
        out = ["CC"] + (["EC"] if props.get("first_ac") else []) + (["2S"] if props.get("type") == "JShtb" else [])
        return out
    flags = [("first_ac", "1A"), ("second_ac", "2A"), ("third_ac", "3A"), ("chair_car", "CC"), ("sleeper", "SL")]
    return [c for f, c in flags if props.get(f)] or ["2S"]


def _km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b_lon - a_lon) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def _near_city(lat: float, lon: float, cities: list[tuple[float, float]]) -> bool:
    return any(_km(lat, lon, c_lat, c_lon) <= CITY_KM for c_lat, c_lon in cities)


def _minutes(value: str | None) -> int | None:
    if not value or value == "None":
        return None
    h, m, *_ = (int(p) for p in value.split(":"))
    return h * 60 + m


def _name(name: str) -> str:
    """Title-case words in capitals ("MYSORE JN" -> "Mysore Jn"); short codes like SF stay."""
    return " ".join(w.title() if w.isupper() and len(w) > 2 else w for w in name.split(" "))


def _keep(props: dict, lat: float, lon: float, bbox: tuple[float, float, float, float] | None) -> bool:
    if bbox is not None:
        return bbox[0] <= lat <= bbox[2] and bbox[1] <= lon <= bbox[3]
    return (props.get("state") or "").strip().lower() in STATES


def build(src: Path, out: Path, bbox: tuple[float, float, float, float] | None = None,
          cities: Path | None = None) -> dict[str, int]:
    stations_raw = json.loads((src / "stations.json").read_text(encoding="utf-8"))
    trains_raw = json.loads((src / "trains.json").read_text(encoding="utf-8"))
    schedules_raw = json.loads((src / "schedules.json").read_text(encoding="utf-8"))

    points = ([(c[1], c[2]) for c in json.loads(cities.read_text(encoding="utf-8"))["cities"].values()]
              if cities else [])
    stations: dict[str, dict] = {}
    boxed: set[str] = set()  # stations kept by the box (or state) filter
    for feat in stations_raw["features"]:
        props = feat["properties"]
        geom = feat.get("geometry")
        if not geom or geom.get("type") != "Point":
            continue
        lon, lat = geom["coordinates"][:2]
        if _keep(props, lat, lon, bbox):
            boxed.add(props["code"])
        elif not (points and _near_city(lat, lon, points)):
            continue
        stations[props["code"]] = {
            "code": props["code"],
            "name": _name(props["name"]),
            "state": props["state"],
            "lat": round(lat, 5),
            "lon": round(lon, 5),
        }

    props_by = {f["properties"]["number"]: f["properties"] for f in trains_raw["features"]}
    by_train: dict[str, list[dict]] = {}
    for row in sorted(schedules_raw, key=lambda r: int(r.get("id") or 0)):
        by_train.setdefault(str(row["train_number"]), []).append(row)

    trains = []
    for number, rows in by_train.items():
        stops = [
            {
                "code": r["station_code"],
                "arr": _minutes(r.get("arrival")),
                "dep": _minutes(r.get("departure")),
                "day": int(r.get("day") or 1),
            }
            for r in rows
        ]
        props = props_by.get(number) or {}
        local = (props.get("type") or "") in LOCAL_TYPES
        kept = [s for s in stops if s["code"] in (boxed if local else stations)]
        if len(kept) >= 2:
            trains.append({"number": number, "name": _name(props.get("name") or number),
                           "type": props.get("type") or "", "classes": classes(props), "stops": kept})

    used = {s["code"] for t in trains for s in t["stops"]}
    out_stations = sorted((stations[c] for c in used), key=lambda s: s["code"])
    trains.sort(key=lambda t: t["number"])

    out.mkdir(parents=True, exist_ok=True)
    for name, payload in (("rail_stations", out_stations), ("rail_trains", trains)):
        text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        data = text.encode("utf-8")
        plain, gz = out / f"{name}.json", out / f"{name}.json.gz"
        plain.unlink(missing_ok=True)
        gz.unlink(missing_ok=True)
        if len(data) > GZIP_OVER:
            gz.write_bytes(gzip.compress(data, mtime=0))
        else:
            plain.write_bytes(data)
    counts = {"stations": len(out_stations), "trains": len(trains)}
    meta = {"source": SOURCE, "licence": LICENCE,
            "filter": {**({"bbox": list(bbox)} if bbox else {"states": sorted(STATES)}),
                       **({"cities_km": CITY_KM, "local_types_outside": sorted(LOCAL_TYPES)} if cities else {})},
            "data_date": "about 2016 (datameet snapshot; timetables are old)",
            "running_days": "not in the source; every train is treated as daily", **counts}
    (out / "rail_meta.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    ap.add_argument("--bbox", help="'demo' or minlat,minlon,maxlat,maxlon; default: the six states")
    ap.add_argument("--cities", action="store_true", help="also stations near the cities in data/cities.json")
    args = ap.parse_args()
    box = None
    if args.bbox:
        box = DEMO_BBOX if args.bbox == "demo" else tuple(float(x) for x in args.bbox.split(","))
    print(build(args.src, args.out, box, CITIES if args.cities else None))
