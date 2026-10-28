"""Cached Google Places API (New) client: text search, details and nearby search.

Every request sends an explicit field mask, has a timeout, and goes through a
cache (Postgres `places_cache`, or in memory for tests). The key comes from the
env var GOOGLE_MAPS_API_KEY. Results are converted to `ty_contracts.Place`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time as _time
import urllib.request
from collections.abc import Callable
from datetime import time
from typing import Any, Protocol

from ty_contracts import Place
from ty_contracts.models import OpeningHours

log = logging.getLogger(__name__)

BASE = "https://places.googleapis.com/v1"
TIMEOUT_S = 8.0
SEARCH_TTL_S = 24 * 3600
DETAILS_TTL_S = 7 * 24 * 3600

# Pro SKU: Text Search and Nearby Search only return name and location at Pro.
LIST_MASK = "places.id,places.displayName,places.location,places.types,places.primaryType"
# Essentials SKU for Details. Opening hours are Enterprise, so opt-in.
DETAILS_MASK = "id,location,types,formattedAddress"
HOURS_MASK = DETAILS_MASK + ",displayName,regularOpeningHours"
# Enterprise Text Search: one call finds the place and its hours (enrichment only).
FIND_HOURS_MASK = "places.id,places.displayName,places.location,places.regularOpeningHours"

EMERGENCY_TYPES = {"hospital": "hospital", "police": "police", "pharmacy": "pharmacy"}
_DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]  # Places: 0 = Sunday

#: (method, url, headers, body, timeout) -> parsed JSON.
Transport = Callable[[str, str, dict[str, str], dict | None, float], dict]


def urllib_transport(method, url, headers, body, timeout):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


class Cache(Protocol):
    def get(self, key: str) -> dict | None: ...
    def set(self, key: str, payload: dict, ttl_s: int) -> None: ...


class MemoryCache:
    def __init__(self, now: Callable[[], float] = _time.time):
        self._now = now
        self._d: dict[str, tuple[dict, float]] = {}

    def get(self, key):
        hit = self._d.get(key)
        return hit[0] if hit and hit[1] > self._now() else None

    def set(self, key, payload, ttl_s):
        self._d[key] = (payload, self._now() + ttl_s)


class PgCache:
    """`places_cache` in Postgres; `conn` is a psycopg connection (autocommit)."""

    def __init__(self, conn: Any):
        self._conn = conn

    def get(self, key):
        row = self._conn.execute(
            "select payload from places_cache where key = %s and expires_at > now()",
            (key,),
        ).fetchone()
        return row[0] if row else None

    def set(self, key, payload, ttl_s):
        self._conn.execute(
            """insert into places_cache (key, payload, expires_at)
               values (%s, %s::jsonb, now() + make_interval(secs => %s))
               on conflict (key) do update set payload = excluded.payload,
                 fetched_at = now(), expires_at = excluded.expires_at""",
            (key, json.dumps(payload), ttl_s),
        )


def _hours(raw: dict) -> list[OpeningHours]:
    out = []
    for p in raw.get("regularOpeningHours", {}).get("periods", []):
        o, c = p.get("open"), p.get("close")
        if not o or not c or "day" not in o:
            continue  # always-open places have no close; nothing to list
        out.append(
            OpeningHours(
                day=_DAYS[o["day"] % 7],
                opens=time(o.get("hour", 0), o.get("minute", 0)),
                closes=time(c.get("hour", 0), c.get("minute", 0)),
            )
        )
    return out


def to_place(raw: dict) -> Place:
    types = raw.get("types") or []
    return Place(
        id=raw["id"],
        name=(raw.get("displayName") or {}).get("text") or raw.get("formattedAddress", ""),
        lat=raw["location"]["latitude"],
        lng=raw["location"]["longitude"],
        category=raw.get("primaryType") or (types[0] if types else "place"),
        opening_hours=_hours(raw),
        typical_visit_minutes=0,  # Places has no dwell time; the guide corpus supplies it
        source="google_places",
    )


class PlacesClient:
    def __init__(
        self,
        cache: Cache | None = None,
        transport: Transport = urllib_transport,
        api_key: str | None = None,
    ):
        self.cache = cache or MemoryCache()
        self._transport = transport
        self._api_key = api_key
        self.calls = 0  # live requests (cache misses), each also logged
        self._count = threading.Lock()

    def _call(self, method: str, path: str, mask: str, body: dict | None, ttl_s: int) -> dict:
        key = hashlib.sha256(
            json.dumps([method, path, mask, body], sort_keys=True).encode()
        ).hexdigest()
        if (hit := self.cache.get(key)) is not None:
            return hit
        api_key = self._api_key or os.environ["GOOGLE_MAPS_API_KEY"]
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": mask,
        }
        with self._count:
            self.calls += 1
        log.warning("places live call: %s %s fields=%s", method, path.split("/")[1][:40], mask)
        payload = self._transport(method, BASE + path, headers, body, TIMEOUT_S)
        self.cache.set(key, payload, ttl_s)
        return payload

    def search(self, query: str, *, limit: int = 5, region: str = "IN") -> list[Place]:
        body = {"textQuery": query, "pageSize": limit, "regionCode": region}
        raw = self._call("POST", "/places:searchText", LIST_MASK, body, SEARCH_TTL_S)
        return [to_place(p) for p in raw.get("places", [])]

    def find_with_hours(
        self, query: str, lat: float, lng: float, *, radius_m: float = 3000
    ) -> dict | None:
        """The best text match near (lat, lng), raw, with regularOpeningHours; None if no match."""
        body = {
            "textQuery": query,
            "pageSize": 1,
            "regionCode": "IN",
            "locationBias": {
                "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_m}
            },
        }
        raw = self._call("POST", "/places:searchText", FIND_HOURS_MASK, body, DETAILS_TTL_S)
        return (raw.get("places") or [None])[0]

    def hours(self, place_id: str) -> list[OpeningHours]:
        """Regular opening hours, per day (Enterprise Details); empty if Places has none."""
        return self.details(place_id, with_hours=True).opening_hours

    def details(self, place_id: str, *, with_hours: bool = False) -> Place:
        mask = HOURS_MASK if with_hours else DETAILS_MASK
        raw = self._call("GET", f"/places/{place_id}", mask, None, DETAILS_TTL_S)
        return to_place(raw)

    def nearby_emergency(
        self, lat: float, lng: float, kind: str = "hospital", *, radius_m: float = 10000, limit: int = 5,
        rank: str = "DISTANCE",
    ) -> list[Place]:
        """rank DISTANCE: the nearest. POPULARITY: Google's prominence, which surfaces the big
        hospitals a few km out that the nearest-N list misses."""
        if kind not in EMERGENCY_TYPES:
            raise ValueError(f"kind must be one of {sorted(EMERGENCY_TYPES)}")
        return self.nearby(lat, lng, EMERGENCY_TYPES[kind], radius_m=radius_m, limit=limit, rank=rank)

    def nearby(
        self, lat: float, lng: float, place_type: str, *, radius_m: float = 3000, limit: int = 5,
        rank: str = "DISTANCE",
    ) -> list[Place]:
        """Places of one Places (New) type near a point: restaurant, vegetarian_restaurant,
        atm, pharmacy, hospital, police. One Nearby Search (Pro), cached a day."""
        body = {
            "includedTypes": [place_type],
            "maxResultCount": limit,
            "rankPreference": rank,
            "locationRestriction": {
                "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_m}
            },
        }
        raw = self._call("POST", "/places:searchNearby", LIST_MASK, body, SEARCH_TTL_S)
        return [to_place(p) for p in raw.get("places", [])]
