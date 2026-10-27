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
}  # fmt: skip
ELDERLY_AGE = 65


def corpus_city(name: str) -> str | None:
    return CITY_ALIASES.get(name.strip().lower())


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
    )


@lru_cache(maxsize=1)
def _pois() -> tuple[dict, ...]:
    return tuple(load_pois()["pois"])


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
