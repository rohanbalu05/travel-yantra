"""Ranked stays for a city, dates and party: Google Hotels through SerpApi when
SERPAPI_API_KEY is set (cached and capped). With the key set and no answer (cap
reached, error), the stays are labelled estimates (one per tier, `sample=True`,
"Estimate: 3-star hotel in Mysuru"), never invented hotels. Without the key (local runs, tests) the fictional sample stays are used,
each marked `sample=True`. Prices are per night for the whole party: hotels
are rooms needed (two to a room) x the room rate, a rental is the whole place.
Every stay carries seller offers (SerpApi's prices by source for the top live
stay, merged with the seller registry's links), stars, guest rating and review
count when Google has them. Cities use the same names and aliases as compare."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

from ty_contracts import Stay

from .compare import UnknownPlace, resolve_city
from .fares import DEFAULT_STYLE, style_key
from .graph import DATA_DIR
from .hotels import Property, SerpApiHotels, default_hotel_provider
from .sellers import ROOM_SLEEPS, Found, StayQuery, stay_offers

PRIOR_RATING, PRIOR_REVIEWS = 4.0, 50  # a few reviews pull a rating towards 4.0 (Bayesian average)
MIN_REVIEWS = 10  # fewer than this, or no rating: shown only when too few rated stays remain
SPARE_BEDROOMS = 1  # a rental may have one bedroom more than the party needs, no more (no 3BHK for two)
GOOD_SCORE = 3.8  # budget style: cheapest among stays at least this good
# When Google Hotels has no answer: one estimate per tier, a room rate per night from the recorded
# Google Hotels searches (Goa, Coorg, Hampi, Chikkamagaluru; 27 Oct 2026): 2-3 star lower quartile,
# 3-star median (17 hotels), 5-star median (6 hotels). The same rate in every city (reversible).
ESTIMATES: tuple[tuple[str, int, int], ...] = (("budget", 2, 2500), ("mid", 3, 4100), ("luxury", 5, 16800))


@lru_cache(maxsize=4)
def _stays(data_dir: Path = DATA_DIR) -> dict[str, list[dict]]:
    raw = json.loads((data_dir / "sample_stays.json").read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _live_rows(props: list[Property]) -> list[dict]:
    return [{"name": p.name, "room_inr": p.room_inr, "rating": p.rating or None, "stars": p.stars,
             "reviews": p.reviews, "kind": p.kind, "bedrooms": p.bedrooms, "token": p.token, "prop": p}
            for p in props]


def _sample_rows(rows: list[dict]) -> list[dict]:
    return [{**r, "kind": "hotel", "sample": True} for r in rows]


def score(r: dict) -> float:
    """Guest rating pulled towards PRIOR_RATING when there are few reviews."""
    if not r.get("rating"):
        return 0.0
    n = r.get("reviews")
    if n is None:
        return r["rating"]  # no count (the samples, some rentals): the rating as it is
    return (r["rating"] * n + PRIOR_RATING * PRIOR_REVIEWS) / (n + PRIOR_REVIEWS)


def suits(r: dict, party: int) -> bool:
    """A rental must sleep the party (two to a bedroom) without bedrooms to spare."""
    if r.get("kind") != "rental" or r.get("bedrooms") is None:
        return True
    need = math.ceil(party / ROOM_SLEEPS)
    return need <= r["bedrooms"] <= need + SPARE_BEDROOMS


def party_price(r: dict, party: int) -> int:
    if r.get("kind") == "rental":
        return r["room_inr"]
    return math.ceil(party / r.get("sleeps", ROOM_SLEEPS)) * r["room_inr"]


def _style_key(style: str | None):
    """Sort key within the stays that fit the budget: budget, cheapest of the good ones;
    mid, 3-4 star (or unrated class) by score then price; luxury, most stars then score."""
    style = style_key(style)
    if style == "budget":
        return lambda r, price: (score(r) < GOOD_SCORE, price, -score(r))
    if style == "luxury":
        return lambda r, price: (-(r.get("stars") or 0), -score(r), price)
    if style == "mid":
        return lambda r, price: (r.get("stars") not in (None, 3, 4), -score(r), price)
    return lambda r, price: (-score(r), price)


def stay_id(city_key: str, r: dict) -> str:
    return f"{city_key}:{r.get('token') or hashlib.sha1(r['name'].encode()).hexdigest()[:12]}"


def rank_stays(city: str, check_in: dt.date, check_out: dt.date, party: int = 1,
               budget_per_night_inr: int | None = None, limit: int = 5,
               data_dir: Path = DATA_DIR, hotels: SerpApiHotels | None = None,
               live: bool = True, budget_style: str | None = None) -> list[Stay]:
    """Up to `limit` stays suited to the party, those within budget_per_night_inr first,
    ordered by budget_style ("budget" | "mid" | "luxury", or shoestring | comfort; None is mid).
    Stays with no rating or few reviews come last. [] when the live search has no answer.
    Raises UnknownPlace for an unknown city, ValueError for bad dates or party."""
    if check_out <= check_in:
        raise ValueError("check_out must be after check_in")
    if party < 1:
        raise ValueError("party must be at least 1")
    node = resolve_city(city)
    key = node.id.removeprefix("PL:")
    hotels = hotels if hotels is not None else (default_hotel_provider() if live else None)
    if hotels is not None:
        rows = _live_rows(hotels.properties(node.name, check_in, check_out) or [])
        if not rows:
            return estimates(node.name, key, check_in, check_out, party, budget_style)[:limit]
    else:
        rows = _sample_rows(_stays(data_dir).get(key) or [])
        if not rows:
            raise UnknownPlace(f"no sample stays in {node.name}")
    rows = [r for r in rows if suits(r, party)]
    by_style = _style_key(budget_style or DEFAULT_STYLE)  # no style said: comfort, as rail (fares.DEFAULT_STYLE)

    def order(r: dict):
        price = party_price(r, party)
        fits = budget_per_night_inr is None or price <= budget_per_night_inr
        rated = bool(r.get("rating")) and (r.get("sample") or (r.get("reviews") or 0) >= MIN_REVIEWS)
        return (not rated, 0, *by_style(r, price)) if fits else (not rated, 1, price)  # over budget: cheapest first

    out = []
    for i, r in enumerate(sorted(rows, key=order)[:limit]):
        prop: Property | None = r.get("prop")
        rooms = 1 if r.get("kind") == "rental" else math.ceil(party / r.get("sleeps", ROOM_SLEEPS))
        found: tuple[Found, ...] = ()
        if prop is not None:
            found = hotels.details(node.name, check_in, check_out, prop) if i == 0 else prop.prices
        # sample names are made up: their links search the city, not the property
        q = StayQuery(node.name, check_in, check_out, adults=party, hotel=r["name"] if prop else None)
        offers = stay_offers(q, [Found(f.seller, f.price_inr * rooms, f.url) for f in found])
        out.append(Stay(id=stay_id(key, r), name=r["name"], city=node.name, check_in=check_in, check_out=check_out,
                        price_per_night_inr=party_price(r, party), offers=offers, stars=r.get("stars"),
                        rating=r.get("rating"), reviews=r.get("reviews"), kind=r.get("kind"),
                        sample=bool(r.get("sample"))))
    return out


def estimates(city: str, key: str, check_in: dt.date, check_out: dt.date, party: int,
              budget_style: str | None = None) -> list[Stay]:
    """Labelled estimate stays (see ESTIMATES), the budget style's tier first, then the
    others from the cheapest; links search the city on each seller."""
    first = style_key(budget_style) if style_key(budget_style) in ("budget", "mid", "luxury") else "mid"
    tiers = sorted(ESTIMATES, key=lambda t: (t[0] != first, t[2]))
    rooms = math.ceil(party / ROOM_SLEEPS)
    q = StayQuery(city, check_in, check_out, adults=party, hotel=None)
    return [Stay(id=f"{key}:estimate-{tier}", name=f"Estimate: {stars}-star hotel in {city}", city=city,
                 check_in=check_in, check_out=check_out, price_per_night_inr=rooms * rate,
                 offers=stay_offers(q, []), stars=stars, kind="hotel", sample=True)
            for tier, stars, rate in tiers]
