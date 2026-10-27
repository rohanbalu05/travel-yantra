"""Google Hotels through SerpApi: properties for a city and dates, and one
property's prices from every source (property details).

Searches ask for two adults (one room), so a rate is per room per night and one
cached answer serves every party size; stays.py multiplies by rooms. Cached 12
hours. Only the top property gets a details call, to keep within the cap."""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from functools import lru_cache

from .sellers import ROOM_SLEEPS, Found
from .serpapi import SerpApi

TTL_S = 12 * 3600


@dataclass(frozen=True)
class Property:
    name: str
    room_inr: int  # lowest rate per room per night
    rating: float
    token: str | None = None
    prices: tuple[Found, ...] = field(default=())  # per room per night, by source


def _rate(d: dict) -> int | None:
    r = (d.get("rate_per_night") or {}).get("extracted_lowest")
    return round(r) if isinstance(r, int | float) else None


def _prices(rows) -> tuple[Found, ...]:
    out = []
    for p in rows or []:
        if p.get("source") and (rate := _rate(p)) is not None:
            out.append(Found(p["source"], rate, p.get("link")))
    return tuple(out)


def parse_properties(payload: dict) -> list[Property]:
    out = []
    for p in payload.get("properties") or []:
        rate = _rate(p)
        if not p.get("name") or rate is None:
            continue
        out.append(Property(p["name"], rate, float(p.get("overall_rating") or 0.0),
                            p.get("property_token"), _prices(p.get("prices"))))
    return out


def parse_details(payload: dict) -> tuple[Found, ...]:
    """featured_prices then prices; one entry per source (the first seen)."""
    seen: dict[str, Found] = {}
    for f in _prices(payload.get("featured_prices")) + _prices(payload.get("prices")):
        seen.setdefault(f.seller, f)
    return tuple(seen.values())


class SerpApiHotels:
    def __init__(self, api: SerpApi | None = None) -> None:
        self.api = api or SerpApi()

    def _base(self, city: str, check_in: dt.date, check_out: dt.date) -> dict:
        return {"engine": "google_hotels", "q": f"hotels in {city}", "check_in_date": check_in.isoformat(),
                "check_out_date": check_out.isoformat(), "adults": str(ROOM_SLEEPS)}

    def properties(self, city: str, check_in: dt.date, check_out: dt.date) -> list[Property] | None:
        payload = self.api.get(self._base(city, check_in, check_out), TTL_S)
        return None if payload is None else parse_properties(payload)

    def details(self, city: str, check_in: dt.date, check_out: dt.date, prop: Property) -> tuple[Found, ...]:
        if not prop.token:
            return prop.prices
        payload = self.api.get({**self._base(city, check_in, check_out), "property_token": prop.token}, TTL_S)
        return prop.prices if payload is None else (parse_details(payload) or prop.prices)


@lru_cache(maxsize=1)
def default_hotel_provider() -> SerpApiHotels | None:
    """Live hotels when SERPAPI_API_KEY is set (cached and capped), else None
    and stays keeps the sample data."""
    return SerpApiHotels() if os.environ.get("SERPAPI_API_KEY") else None
