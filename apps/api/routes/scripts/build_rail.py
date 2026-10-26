"""Build the processed rail subset from datameet/railways (CC0) raw files.

Usage:
    python build_rail.py --src <dir with stations.json trains.json schedules.json> \
        --out apps/api/routes/data

Keeps stations in Karnataka, Goa, Maharashtra, Kerala, Tamil Nadu and Andhra
Pradesh, and trains that stop at two or more of them. Output files are
gzipped when larger than 5 MB.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

STATES = {"karnataka", "goa", "maharashtra", "kerala", "tamil nadu", "andhra pradesh"}
GZIP_OVER = 5 * 1024 * 1024


def _minutes(value: str | None) -> int | None:
    if not value or value == "None":
        return None
    h, m, *_ = (int(p) for p in value.split(":"))
    return h * 60 + m


def build(src: Path, out: Path) -> dict[str, int]:
    stations_raw = json.loads((src / "stations.json").read_text(encoding="utf-8"))
    trains_raw = json.loads((src / "trains.json").read_text(encoding="utf-8"))
    schedules_raw = json.loads((src / "schedules.json").read_text(encoding="utf-8"))

    stations: dict[str, dict] = {}
    for feat in stations_raw["features"]:
        props = feat["properties"]
        geom = feat.get("geometry")
        state = (props.get("state") or "").strip().lower()
        if state not in STATES or not geom or geom.get("type") != "Point":
            continue
        lon, lat = geom["coordinates"][:2]
        stations[props["code"]] = {
            "code": props["code"],
            "name": props["name"],
            "state": props["state"],
            "lat": round(lat, 5),
            "lon": round(lon, 5),
        }

    names = {f["properties"]["number"]: f["properties"]["name"] for f in trains_raw["features"]}
    by_train: dict[str, list[dict]] = {}
    for row in schedules_raw:
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
        kept = [s for s in stops if s["code"] in stations]
        if len(kept) >= 2:
            trains.append({"number": number, "name": names.get(number, number), "stops": kept})

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
    return {"stations": len(out_stations), "trains": len(trains)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    args = ap.parse_args()
    print(build(args.src, args.out))
