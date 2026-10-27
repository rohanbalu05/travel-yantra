"""Google Flights through SerpApi: one-way economy flights for an airport pair
and date, and the sellers' prices for one flight (booking options).

Searches ask for one adult, so prices are per person and one cached answer
serves every party size; compare multiplies by travellers. Cached 6 hours."""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from .sellers import Found
from .serpapi import SerpApi

TTL_S = 6 * 3600


@dataclass(frozen=True)
class Flight:
    origin: str  # IATA
    destination: str
    depart: dt.datetime
    arrive: dt.datetime
    minutes: int
    price_inr: int  # per person
    airline: str
    number: str  # "6E 6211", or "6E 6211 + 6E 302" with a stop
    stops: int
    booking_token: str | None = None


class FlightProvider(Protocol):
    def flights(self, origin: str, destination: str, date: dt.date) -> list[Flight] | None: ...
    def booking(self, flight: Flight) -> list[Found]: ...


def _time(s: str) -> dt.datetime:
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M")


def parse_flights(payload: dict, origin: str, destination: str) -> list[Flight]:
    """best_flights then other_flights; groups without a price or times are skipped."""
    out = []
    for group in (payload.get("best_flights") or []) + (payload.get("other_flights") or []):
        segs = group.get("flights") or []
        price = group.get("price")
        try:
            depart = _time(segs[0]["departure_airport"]["time"])
            arrive = _time(segs[-1]["arrival_airport"]["time"])
        except (IndexError, KeyError, TypeError, ValueError):
            continue
        if not isinstance(price, int | float) or arrive <= depart:
            continue
        minutes = int(group.get("total_duration") or (arrive - depart).total_seconds() // 60)
        out.append(Flight(origin, destination, depart, arrive, minutes, round(price),
                          segs[0].get("airline") or "", " + ".join(s.get("flight_number", "") for s in segs),
                          len(segs) - 1, group.get("booking_token")))
    return out


def parse_booking(payload: dict) -> list[Found]:
    out = []
    for opt in payload.get("booking_options") or []:
        t = opt.get("together") or {}
        price = t.get("price")
        if t.get("book_with") and isinstance(price, int | float):
            out.append(Found(t["book_with"], round(price)))  # booking_request needs a POST: no URL kept
    return out


class SerpApiFlights:
    def __init__(self, api: SerpApi | None = None) -> None:
        self.api = api or SerpApi()

    def _base(self, origin: str, destination: str, date: dt.date) -> dict:
        return {"engine": "google_flights", "departure_id": origin, "arrival_id": destination,
                "outbound_date": date.isoformat(), "type": "2", "adults": "1", "travel_class": "1"}

    def flights(self, origin, destination, date):
        payload = self.api.get(self._base(origin, destination, date), TTL_S)
        return None if payload is None else parse_flights(payload, origin, destination)

    def booking(self, flight):
        if not flight.booking_token:
            return []
        params = {**self._base(flight.origin, flight.destination, flight.depart.date()),
                  "booking_token": flight.booking_token}
        payload = self.api.get(params, TTL_S)
        return [] if payload is None else parse_booking(payload)


@lru_cache(maxsize=1)
def default_flight_provider() -> SerpApiFlights | None:
    """Live flights when SERPAPI_API_KEY is set (cached and capped), else None
    and compare keeps the fake air network."""
    return SerpApiFlights() if os.environ.get("SERPAPI_API_KEY") else None
