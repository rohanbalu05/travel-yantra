"""Seller registry: booking links for flights and stays, merged with SerpApi
prices so one booking shows every seller.

Booking.com, Airbnb and MakeMyTrip get deep links (the search filled in, no API
keys); Goibibo, Cleartrip and ixigo get a "Check price" link to their search.
A seller that SerpApi names but the registry does not know keeps SerpApi's link
when it gave one (kind deep_link), else gets a Google search "Check price" link.
No affiliate parameters."""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from ty_contracts import SellerOffer

ROOM_SLEEPS = 2  # rooms asked for = ceil(adults / 2)


@dataclass(frozen=True)
class FlightQuery:
    origin: str  # IATA code
    destination: str
    date: dt.date
    adults: int = 1


@dataclass(frozen=True)
class StayQuery:
    city: str
    check_in: dt.date
    check_out: dt.date
    adults: int = 1
    hotel: str | None = None  # a property name narrows the search where the seller allows it

    @property
    def rooms(self) -> int:
        return max(1, math.ceil(self.adults / ROOM_SLEEPS))


@dataclass(frozen=True)
class Found:
    """A price one seller quoted (from SerpApi)."""

    seller: str
    price_inr: int | None
    url: str | None = None


def _q(params: dict) -> str:
    return urlencode(params, quote_via=quote)


def _flight_links(f: FlightQuery) -> dict[str, tuple[str, str]]:
    d = f.date
    return {
        "MakeMyTrip": ("deep_link", "https://www.makemytrip.com/flight/search?" + _q({
            "itinerary": f"{f.origin}-{f.destination}-{d:%d/%m/%Y}", "tripType": "O",
            "paxType": f"A-{f.adults}_C-0_I-0", "intl": "false", "cabinClass": "E"})),
        "Goibibo": ("check_price", f"https://www.goibibo.com/flights/air-{f.origin}-{f.destination}-{d:%Y%m%d}--{f.adults}-0-0-E-D/"),
        "Cleartrip": ("check_price", "https://www.cleartrip.com/flights/results?" + _q({
            "adults": f.adults, "childs": 0, "infants": 0, "class": "Economy",
            "depart_date": f"{d:%d/%m/%Y}", "from": f.origin, "to": f.destination, "intl": "n"})),
        "ixigo": ("check_price", "https://www.ixigo.com/search/result/flight?" + _q({
            "from": f.origin, "to": f.destination, "date": f"{d:%d%m%Y}", "adults": f.adults,
            "children": 0, "infants": 0, "class": "e"})),
    }


def _stay_links(s: StayQuery) -> dict[str, tuple[str, str]]:
    where = f"{s.hotel}, {s.city}" if s.hotel else s.city
    return {
        "Booking.com": ("deep_link", "https://www.booking.com/searchresults.html?" + _q({
            "ss": where, "checkin": s.check_in.isoformat(), "checkout": s.check_out.isoformat(),
            "group_adults": s.adults, "no_rooms": s.rooms, "group_children": 0})),
        "Airbnb": ("deep_link", f"https://www.airbnb.co.in/s/{quote(s.city)}/homes?" + _q({
            "checkin": s.check_in.isoformat(), "checkout": s.check_out.isoformat(), "adults": s.adults})),
        "MakeMyTrip": ("deep_link", "https://www.makemytrip.com/hotels/hotel-listing/?" + _q({
            "checkin": f"{s.check_in:%m%d%Y}", "checkout": f"{s.check_out:%m%d%Y}",
            "roomStayQualifier": f"{s.adults}e0e", "searchText": where})),
        "Goibibo": ("check_price", "https://www.goibibo.com/hotels/?" + _q({"q": where})),
        "Cleartrip": ("check_price", "https://www.cleartrip.com/hotels/results?" + _q({
            "city": s.city, "chk_in": f"{s.check_in:%d/%m/%Y}", "chk_out": f"{s.check_out:%d/%m/%Y}",
            "adults1": s.adults, "num_rooms": s.rooms})),
        "ixigo": ("check_price", "https://www.ixigo.com/hotels/search/result?" + _q({
            "searchText": where, "checkinDate": f"{s.check_in:%d%m%Y}",
            "checkoutDate": f"{s.check_out:%d%m%Y}", "adults": s.adults})),
    }


def _google(text: str) -> str:
    return "https://www.google.com/search?" + _q({"q": text})


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _merge(links: dict[str, tuple[str, str]], found: list[Found], fallback_text: str,
           prefer_found_url: bool, at: dt.datetime) -> list[SellerOffer]:
    known = {_norm(k): k for k in links}
    offers: dict[str, SellerOffer] = {
        k: SellerOffer(seller=k, url=url, kind=kind, fetched_at=at) for k, (kind, url) in links.items()}
    for f in found:
        name = known.get(_norm(f.seller), f.seller)
        have = offers.get(name)
        if have is not None and have.price_inr is not None and f.price_inr is not None and have.price_inr <= f.price_inr:
            continue  # keep the seller's cheapest quote
        if have is not None and not (prefer_found_url and f.url):
            url, kind = have.url, have.kind
        elif f.url and f.url.startswith("https://"):
            url, kind = f.url, "deep_link"
        else:
            url, kind = _google(f"{f.seller} {fallback_text}"), "check_price"
        offers[name] = SellerOffer(seller=name, price_inr=f.price_inr, url=url, kind=kind, fetched_at=at)
    # priced offers cheapest first, then the rest in registry order
    order = {k: i for i, k in enumerate(offers)}
    return sorted(offers.values(), key=lambda o: (o.price_inr is None, o.price_inr or 0, order[o.seller]))


def flight_offers(q: FlightQuery, found: list[Found] = (), at: dt.datetime | None = None) -> list[SellerOffer]:
    """Every seller for one flight search. SerpApi's flight booking links need a
    POST, so known sellers keep the registry link and unknown ones a Google search."""
    at = at or dt.datetime.now(dt.UTC)
    return _merge(_flight_links(q), list(found), f"flight {q.origin} to {q.destination} {q.date:%d %b %Y}",
                  prefer_found_url=False, at=at)


def stay_offers(q: StayQuery, found: list[Found] = (), at: dt.datetime | None = None) -> list[SellerOffer]:
    """Every seller for one stay. SerpApi's per-property links win over the
    registry's search links for the same seller."""
    at = at or dt.datetime.now(dt.UTC)
    return _merge(_stay_links(q), list(found), f"{q.hotel or 'hotels'} {q.city}",
                  prefer_found_url=True, at=at)
