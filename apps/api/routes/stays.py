"""Ranked stays for a city, dates and party: Google Hotels through SerpApi when
SERPAPI_API_KEY is set (cached and capped), else fictional sample data. Prices
are per night for the whole party (rooms needed x room rate). Every stay
carries seller offers: SerpApi's prices by source (the top live stay only)
merged with the seller registry's links. Cities use the same names and
aliases as compare."""
from __future__ import annotations

import datetime as dt
import json
import math
from functools import lru_cache
from pathlib import Path

from ty_contracts import Stay

from .compare import UnknownPlace, resolve_city
from .graph import DATA_DIR
from .hotels import Property, SerpApiHotels, default_hotel_provider
from .sellers import Found, StayQuery, stay_offers


@lru_cache(maxsize=4)
def _stays(data_dir: Path = DATA_DIR) -> dict[str, list[dict]]:
    raw = json.loads((data_dir / "sample_stays.json").read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _live_rows(hotels: SerpApiHotels, city: str, check_in: dt.date, check_out: dt.date) -> list[dict]:
    props = hotels.properties(city, check_in, check_out) or []
    return [{"name": p.name, "room_inr": p.room_inr, "rating": p.rating, "sleeps": 2, "prop": p} for p in props]


def rank_stays(city: str, check_in: dt.date, check_out: dt.date, party: int = 1,
               budget_per_night_inr: int | None = None, limit: int = 3,
               data_dir: Path = DATA_DIR, hotels: SerpApiHotels | None = None,
               live: bool = True) -> list[Stay]:
    """Stays that fit the budget first (best rating, then cheapest), then the
    rest by price. Raises UnknownPlace for a city outside the sample, and
    ValueError for bad dates or party."""
    if check_out <= check_in:
        raise ValueError("check_out must be after check_in")
    if party < 1:
        raise ValueError("party must be at least 1")
    node = resolve_city(city)
    hotels = hotels if hotels is not None else (default_hotel_provider() if live else None)
    rows = _live_rows(hotels, node.name, check_in, check_out) if hotels else []
    if not rows:
        rows = _stays(data_dir).get(node.id.removeprefix("PL:"))
    if not rows:
        raise UnknownPlace(f"no sample stays in {node.name}")
    priced = [(r, math.ceil(party / r["sleeps"])) for r in rows]

    def key(item: tuple[dict, int]):
        r, rooms = item
        price = rooms * r["room_inr"]
        fits = budget_per_night_inr is None or price <= budget_per_night_inr
        return (0, -r["rating"], price) if fits else (1, price, -r["rating"])

    out = []
    for i, (r, rooms) in enumerate(sorted(priced, key=key)[:limit]):
        prop: Property | None = r.get("prop")
        found: tuple[Found, ...] = ()
        if prop is not None:
            found = hotels.details(node.name, check_in, check_out, prop) if i == 0 else prop.prices
        # sample names are made up: their links search the city, not the property
        q = StayQuery(node.name, check_in, check_out, adults=party, hotel=r["name"] if prop else None)
        offers = stay_offers(q, [Found(f.seller, f.price_inr * rooms, f.url) for f in found])
        out.append(Stay(name=r["name"], city=node.name, check_in=check_in, check_out=check_out,
                        price_per_night_inr=rooms * r["room_inr"], offers=offers))
    return out
