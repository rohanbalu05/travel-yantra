"""Fill opening hours of corridor POIs from Google Places API (New). Goa first.

    cd apps/api && uv run python -m guide.scripts.enrich_places [goa] [--refresh]

One Enterprise Text Search per place (name + region, biased to the Wikidata
coordinates) returns the place id and its regular opening hours. A match more
than MAX_KM from our coordinates is rejected. Places has no admission-fee field,
so every fee stays tagged fee-unverified; hours Places can't confirm stay
hours-unverified. Places already checked are skipped unless --refresh.

Every live call is counted against MAX_CALLS and appended to
data/corridor/places_calls.log; responses are cached in .lanes/ (not committed),
so a re-run costs nothing. Needs GOOGLE_MAPS_API_KEY.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

from guide.places import PlacesClient, urllib_transport
from guide.retrieval.seed import DATA

OUT = DATA / "corridor"
LOG = OUT / "places_calls.log"
CACHE = DATA.parent / ".lanes" / "places-cache.json"
MAX_CALLS = 40  # per run, HQ's cap for P4
MAX_KM = 3.0  # beaches, falls and islands are big; a fort 3 km off is another place
REGION_QUERY = {"goa": "Goa, India"}


class BudgetSpent(RuntimeError):
    pass


class FileCache:
    """Places responses on disk, so re-runs and refreshes of the data file are free."""

    def __init__(self, path: Path):
        self.path = path
        self._d = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def get(self, key):
        return self._d.get(key)

    def set(self, key, payload, ttl_s):  # one-off enrichment: kept until deleted
        self._d[key] = payload
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(self._d, ensure_ascii=False), encoding="utf-8")


class CountingTransport:
    def __init__(self, transport, budget: int, log: Path | None = None):
        self.transport, self.budget, self.log, self.calls = transport, budget, log, 0

    def __call__(self, method, url, headers, body, timeout):
        if self.calls >= self.budget:
            raise BudgetSpent(f"Places call budget of {self.budget} spent")
        self.calls += 1
        query = (body or {}).get("textQuery", url.rsplit("/", 1)[-1])
        try:
            out = self.transport(method, url, headers, body, timeout)
        except Exception as e:
            self._write(f"{query}\terror {type(e).__name__}")
            raise
        self._write(f"{query}\tok")
        return out

    def _write(self, line: str) -> None:
        if self.log:
            stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            with self.log.open("a", encoding="utf-8") as f:
                f.write(f"{stamp}\ttext_search_enterprise\t{line}\n")


def km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)  # fmt: skip
    return 6371 * 2 * math.asin(math.sqrt(a))


def _hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def hours_from(raw_hours: dict | None) -> dict | None:
    """Places regularOpeningHours -> corpus opens/closes/closed_on, or None if absent.

    The corpus keeps one opening and one closing time, so they are the most common
    first opening and last closing across open days; a midday break or a day with
    different hours adds a tag, and hours_text keeps Places' own wording."""
    periods = (raw_hours or {}).get("periods") or []
    if not periods:
        return None
    days: dict[int, list[tuple[int, int]]] = {}
    for p in periods:
        o, c = p.get("open") or {}, p.get("close")
        if "day" not in o:
            continue
        iso = o["day"] or 7  # Places 0 = Sunday; corpus closed_on 1 = Mon .. 7 = Sun
        start = o.get("hour", 0) * 60 + o.get("minute", 0)
        if c is None:  # open 24 hours
            end = 24 * 60 - 1
        elif c.get("day") != o["day"]:
            end = 24 * 60 - 1  # past midnight: the corpus can't say so, close at 23:59
        else:
            end = c.get("hour", 0) * 60 + c.get("minute", 0)
        days.setdefault(iso, []).append((start, end))
    if not days:
        return None
    if len(periods) == 1 and periods[0].get("close") is None:
        days = {d: [(0, 24 * 60 - 1)] for d in range(1, 8)}  # one open-only period = always open
    firsts = Counter(min(s for s, _ in v) for v in days.values())
    lasts = Counter(max(e for _, e in v) for v in days.values())
    tags = []
    if any(len(v) > 1 for v in days.values()):
        tags.append("hours-break")
    if len(firsts) > 1 or len(lasts) > 1:
        tags.append("hours-vary")
    return {
        "opens": _hhmm(firsts.most_common(1)[0][0]),
        "closes": _hhmm(lasts.most_common(1)[0][0]),
        "closed_on": sorted(set(range(1, 8)) - set(days)),
        "tags": tags,
        "text": (raw_hours or {}).get("weekdayDescriptions") or [],
    }


def enrich(poi: dict, found: dict | None, today: str) -> dict:
    """A copy of poi with what Places confirmed; unconfirmed fields stay as they were."""
    out = dict(poi)
    out["hours_checked"] = today
    tags = [t for t in poi.get("tags") or [] if t not in ("hours-break", "hours-vary", "hours-places")]
    if found is None:
        out["places_status"] = "not-found"
    elif km(poi["lat"], poi["lng"], found["location"]["latitude"], found["location"]["longitude"]) > MAX_KM:
        out["places_status"] = "no-match"
    elif (h := hours_from(found.get("regularOpeningHours"))) is None:
        out["places_status"] = "no-hours"
        out["place_id"] = found["id"]
    else:
        out["places_status"] = "hours"
        out["place_id"] = found["id"]
        out.update(opens=h["opens"], closes=h["closes"], closed_on=h["closed_on"])
        out["hours_text"] = h["text"]
        out["hours_source"] = "google_places"
        tags = [t for t in tags if t != "hours-unverified"] + ["hours-places"] + h["tags"]
    if out["places_status"] != "hours" and "hours-unverified" not in tags:
        tags.append("hours-unverified")
    if "fee-unverified" not in tags and "entry_fee_inr" not in poi:
        tags.append("fee-unverified")  # Places has no admission fees
    out["tags"] = tags
    return out


def run(region: str, client: PlacesClient, *, refresh: bool = False, today: str | None = None) -> Counter:
    path = OUT / f"{region}_pois.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    today = today or date.today().isoformat()
    status: Counter = Counter()
    pois = []
    try:
        for poi in data["pois"]:
            if poi.get("hours_checked") and not refresh:
                pois.append(poi)
                status["skipped"] += 1
                continue
            found = client.find_with_hours(f"{poi['name']}, {REGION_QUERY[region]}", poi["lat"], poi["lng"])
            poi = enrich(poi, found, today)
            status[poi["places_status"]] += 1
            pois.append(poi)
    except BudgetSpent:
        status["budget-stop"] += 1
        pois += data["pois"][len(pois):]  # the rest unchanged; a re-run picks them up
    data["pois"] = pois
    data["_places"] = (
        "Opening hours with tag hours-places come from Google Places API (New) on the "
        "hours_checked date (place_id kept). Places has no admission fees, so fees stay "
        "fee-unverified; hours-unverified means Places had no match or no hours."
    )
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return status


def main(argv: list[str]) -> None:
    refresh = "--refresh" in argv
    regions = [a for a in argv if not a.startswith("--")] or list(REGION_QUERY)
    transport = CountingTransport(urllib_transport, MAX_CALLS, LOG)
    client = PlacesClient(cache=FileCache(CACHE), transport=transport)
    for region in regions:
        print(f"{region}: {dict(run(region, client, refresh=refresh))}")
    print(f"Places live calls: {transport.calls} (cap {MAX_CALLS})")


if __name__ == "__main__":
    main(sys.argv[1:])
