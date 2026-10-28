"""Places for the trip planner, straight from the curated corpus (data/pois.json).

No database and no network: the planner runs in tests and before Cloud SQL exists.
Ids are stable slugs (city + name), so a revise can exclude what is already planned.
"""

from __future__ import annotations

import re
from datetime import time
from functools import lru_cache

from ty_contracts import Lang, OpeningHours, Place, TripRequest

from .retrieval.seed import load_pois

SOURCE = "travel_yantra_corpus"
_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # corpus closed_on: 1 = Mon

#: Spellings travellers type -> the corpus city.
CITY_ALIASES = {
    "mysore": "Mysuru", "mysuru": "Mysuru", "srirangapatna": "Mysuru",
    "bangalore": "Bengaluru", "bengaluru": "Bengaluru",
    "hampi": "Hampi", "hosapete": "Hampi", "hospet": "Hampi",
    "coorg": "Coorg", "kodagu": "Coorg", "madikeri": "Coorg",
    "chikmagalur": "Chikmagalur", "chikkamagaluru": "Chikmagalur",
    "belur": "Chikmagalur", "halebidu": "Chikmagalur",
    "goa": "Goa", "panaji": "Goa", "panjim": "Goa", "old goa": "Goa", "margao": "Goa",
    "madgaon": "Goa", "north goa": "Goa", "south goa": "Goa", "mapusa": "Goa",
    "kochi": "Kochi", "cochin": "Kochi", "fort kochi": "Kochi", "ernakulam": "Kochi",
    "mattancherry": "Kochi",
    "munnar": "Munnar",
    "alleppey": "Alleppey", "alappuzha": "Alleppey", "kumarakom": "Alleppey", "kuttanad": "Alleppey",
    "delhi": "Delhi", "new delhi": "Delhi", "old delhi": "Delhi",
    "agra": "Agra", "fatehpur sikri": "Agra",
    "jaipur": "Jaipur", "amer": "Jaipur", "amber": "Jaipur", "pink city": "Jaipur",
}  # fmt: skip
ELDERLY_AGE = 65
#: Corpus city -> the region it belongs to (what the planner can tell travellers it covers).
REGIONS = {
    "Mysuru": "Karnataka", "Bengaluru": "Karnataka", "Hampi": "Karnataka", "Coorg": "Karnataka",
    "Chikmagalur": "Karnataka", "Goa": "Goa",
    "Kochi": "Kerala", "Munnar": "Kerala", "Alleppey": "Kerala",
    "Delhi": "Golden Triangle", "Agra": "Golden Triangle", "Jaipur": "Golden Triangle",
}  # fmt: skip
#: Under a roof: museums and temples, palaces (their interiors), churches and tombs, or
#: the "indoor" tag. Never ruins, hilltops, viewpoints or Hampi's open temple complexes,
#: or the "outdoor" tag. Forts, gardens, markets and food stops are not.
INDOOR_CATEGORIES = {"museum", "temple"}
INDOOR_NAME = re.compile(r"church|cathedral|basilica|mausoleum|gumbaz|tomb|mahal|palace|haveli", re.I)
OUTDOOR_TAGS = {"outdoor", "ruins", "hilltop", "viewpoint", "stepwell"}
OPEN_AIR_CITIES = {"Hampi"}  # a ruined city: its temples have no roof worth the name in rain


def covered_cities() -> dict[str, str]:
    """{corpus city: region} for every city the corpus holds places for."""
    have = {p["city"] for p in _pois()}
    return {city: region for city, region in REGIONS.items() if city in have}


@lru_cache(maxsize=1)
def indoor_ids() -> frozenset[str]:
    """Planner ids of places a rain plan can use: an indoor category or the "indoor" tag,
    never one tagged "outdoor" (an open-air temple complex), never food."""
    out = set()
    for p in _pois():
        tags = set(p.get("tags") or [])
        if p["category"] == "museum" or "indoor" in tags:
            out.add(_slug(f"{p['city']} {p['name']}"))
        elif tags & OUTDOOR_TAGS or p["city"] in OPEN_AIR_CITIES or p["category"] not in (
                *INDOOR_CATEGORIES, "monument"):  # fmt: skip
            continue
        elif p["category"] in INDOOR_CATEGORIES or "palace" in tags or INDOOR_NAME.search(p["name"]):
            out.add(_slug(f"{p['city']} {p['name']}"))
    return frozenset(out)


def is_indoor(place: Place) -> bool:
    return place.id in indoor_ids()


def exact_city(name: str) -> str | None:
    """The corpus city a name spells exactly: an alias as typed, or normalized ("the city of
    Mysore", "मैसूर", "ಮೈಸೂರು"). No fuzzy match: "Hampi" is Hampi, never Hampi Bazaar."""
    if hit := CITY_ALIASES.get(name.strip().lower()):
        return hit
    from . import names

    norm = " ".join(w for w in names.normalize(name).split() if w not in ("city", "town"))
    if not norm:
        return None
    return {names.normalize(alias): city for alias, city in CITY_ALIASES.items()}.get(norm)


def corpus_city(name: str) -> str | None:
    """The corpus city a traveller means: exact_city, then difflib with one clear winner
    ("Mysuuru")."""
    if hit := exact_city(name):
        return hit
    from . import names

    norm = " ".join(w for w in names.normalize(name).split() if w not in ("city", "town"))
    alias = names.best(norm, CITY_ALIASES) if norm else None
    return CITY_ALIASES[alias] if alias else None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace("'", "")).strip("-")


def _hours(p: dict) -> list[OpeningHours]:
    if not p.get("opens") or not p.get("closes"):
        return []  # not known (corridor places from Wikimedia): the solver treats it as open
    opens, closes = time.fromisoformat(p["opens"]), time.fromisoformat(p["closes"])
    closed = set(p.get("closed_on") or [])
    return [
        OpeningHours(day=d, opens=opens, closes=closes)
        for n, d in enumerate(_DAYS, start=1)
        if n not in closed
    ]


def to_place(p: dict) -> Place:
    return Place(
        id=_slug(f"{p['city']} {p['name']}"),
        name=p["name"],
        native_names=p.get("names") or ({Lang.kn: p["name_kn"]} if p.get("name_kn") else {}),
        lat=p["lat"],
        lng=p["lng"],
        category=p["category"],
        opening_hours=_hours(p),
        typical_visit_minutes=p["typical_dwell_min"],
        source=SOURCE,
        ticket_url=p.get("ticket_url"),  # the official site only; None where there is none
    )


@lru_cache(maxsize=1)
def _pois() -> tuple[dict, ...]:
    return tuple(load_pois()["pois"])


@lru_cache(maxsize=1)
def place_ids() -> dict[str, str]:
    """Planner id -> Google place_id, for corpus places Places matched and has hours for.
    The repo keeps only the id (Places terms); guide.hours fetches the hours."""
    return {
        _slug(f"{p['city']} {p['name']}"): p["place_id"]
        for p in _pois() if p.get("place_id") and p.get("places_status") == "hours"
    }  # fmt: skip


def places_for(
    city: str,
    *,
    elderly: bool = False,
    categories: set[str] | None = None,
    exclude: set[str] | frozenset[str] = frozenset(),
    limit: int | None = None,
) -> list[Place]:
    """The city's places, best first: popularity, then (for an elderly party) the
    elderly-friendly ones, then name. Unknown city: an empty list."""
    wanted = corpus_city(city)
    pois = [
        p for p in _pois()
        if p["city"] == wanted and (not categories or p["category"] in categories)
    ]  # fmt: skip
    pois.sort(key=lambda p: (
        -(p.get("popularity") or 0),
        elderly and p.get("elderly_friendly") is False,
        p["name"],
    ))  # fmt: skip
    out = [pl for pl in map(to_place, pois) if pl.id not in exclude]
    return out[:limit] if limit else out


def places_for_request(request: TripRequest, *, exclude: frozenset[str] = frozenset()) -> list[Place]:
    """Every destination's places, ranked within each city, in destination order."""
    c = request.constraints
    elderly = bool(c.mobility_needs) or any(t.age >= ELDERLY_AGE for t in c.travellers)
    out: list[Place] = []
    for city in request.destinations:
        out += places_for(city, elderly=elderly, exclude=exclude)
    return out
