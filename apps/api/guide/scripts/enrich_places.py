"""Match corridor POIs to Google Places (API New) and keep only their place_id. Goa first.

    cd apps/api && uv run python -m guide.scripts.enrich_places [goa] [--refresh]

One Enterprise Text Search per place (name + region, biased to the Wikidata
coordinates) finds the place and whether Places has opening hours for it. A match
more than MAX_KM from our coordinates is rejected. Places terms let us store the
place_id and nothing else (V3-AD), so the repo gets the id and a status; the
hours are fetched at runtime by guide.hours. Hours stay tagged hours-unverified in
the repo and every fee fee-unverified (Places has no admission fees). Places
already checked are skipped unless --refresh.

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
REGION_QUERY = {
    "goa": "Goa, India", "kochi": "Kochi, Kerala, India", "munnar": "Munnar, Kerala, India",
    "alleppey": "Alappuzha, Kerala, India", "delhi": "Delhi, India", "agra": "Agra, Uttar Pradesh, India",
    "jaipur": "Jaipur, Rajasthan, India",
}  # fmt: skip


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


#: Tags an earlier run derived from Places' hours: Places content, so never kept.
DERIVED_TAGS = {"hours-places", "hours-break", "hours-vary"}
#: Fields an earlier run copied from Places: dropped, the corpus has no hours of its own.
DERIVED_FIELDS = ("hours_text", "hours_source")


def enrich(poi: dict, found: dict | None, today: str) -> dict:
    """A copy of poi with the Places match: place_id and places_status, nothing else."""
    out = {k: v for k, v in poi.items() if k not in DERIVED_FIELDS and k != "place_id"}
    if poi.get("hours_source") == "google_places":  # hours an earlier run copied in
        out.update(opens=None, closes=None, closed_on=[])
    out["hours_checked"] = today
    if found is None:
        out["places_status"] = "not-found"
    elif km(poi["lat"], poi["lng"], found["location"]["latitude"], found["location"]["longitude"]) > MAX_KM:
        out["places_status"] = "no-match"
    else:
        out["place_id"] = found["id"]
        periods = (found.get("regularOpeningHours") or {}).get("periods")
        out["places_status"] = "hours" if periods else "no-hours"
    tags = [t for t in poi.get("tags") or [] if t not in DERIVED_TAGS]
    if not out.get("opens") and "hours-unverified" not in tags:
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
        "place_id and places_status come from Google Places API (New) on the hours_checked "
        "date. Places terms allow storing the id only, so hours are fetched at runtime "
        "(guide.hours) where places_status is 'hours'. Places has no admission fees, so "
        "fees stay fee-unverified."
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
