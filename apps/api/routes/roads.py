"""Road edges from the Google Routes API (computeRoutes), cached and capped, with
the haversine fake as fallback.

Uses TRAFFIC_UNAWARE routing and a duration+distance field mask so every call
stays on the Essentials SKU inside the free cap. The key comes from the env var
GOOGLE_MAPS_API_KEY; without it no call is made. Tests pass a fake transport."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time as _time
import urllib.request
from collections.abc import Callable
from typing import Protocol

from .graph import COMFORT, ROAD_INR_PER_KM, Edge, HaversineRoadProvider, Node

URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = "routes.duration,routes.distanceMeters"
TIMEOUT_S = 8.0
TTL_S = 7 * 24 * 3600
MAX_LIVE_CALLS = 100  # per process; the free cap is monthly, this keeps one instance well inside it
REF = "routes_api"

log = logging.getLogger(__name__)

#: (url, headers, body, timeout) -> parsed JSON.
Transport = Callable[[str, dict[str, str], dict, float], dict]


def urllib_transport(url, headers, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
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


def _point(n: Node) -> dict:
    return {"location": {"latLng": {"latitude": round(n.lat, 5), "longitude": round(n.lon, 5)}}}


class RoutesApiRoadProvider:
    """RoadEdgeProvider backed by computeRoutes; falls back to haversine on no key,
    cap reached, error or no route."""

    def __init__(self, cache: Cache | None = None, transport: Transport = urllib_transport,
                 api_key: str | None = None, max_live_calls: int = MAX_LIVE_CALLS,
                 fallback: HaversineRoadProvider | None = None) -> None:
        self.cache = cache or MemoryCache()
        self._transport = transport
        self._api_key = api_key
        self.max_live_calls = max_live_calls
        self.fallback = fallback or HaversineRoadProvider()
        self.live_calls = 0

    def _key(self) -> str | None:
        return self._api_key or os.environ.get("GOOGLE_MAPS_API_KEY")

    def _route(self, a: Node, b: Node) -> dict | None:
        body = {"origin": _point(a), "destination": _point(b), "travelMode": "DRIVE",
                "routingPreference": "TRAFFIC_UNAWARE"}
        ck = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        if (hit := self.cache.get(ck)) is not None:
            return hit
        key = self._key()
        if not key or self.live_calls >= self.max_live_calls:
            return None
        self.live_calls += 1
        headers = {"Content-Type": "application/json", "X-Goog-Api-Key": key,
                   "X-Goog-FieldMask": FIELD_MASK}
        try:
            payload = self._transport(URL, headers, body, TIMEOUT_S)
        except Exception as exc:  # network, HTTP or JSON error: fall back, never fail the request
            log.warning("routes api call failed (%s); using haversine", type(exc).__name__)
            return None
        self.cache.set(ck, payload, TTL_S)
        log.info("routes api live call %d/%d", self.live_calls, self.max_live_calls)
        return payload

    def road_edge(self, a: Node, b: Node) -> Edge | None:
        payload = self._route(a, b)
        routes = (payload or {}).get("routes") or []
        if routes and "duration" in routes[0] and "distanceMeters" in routes[0]:
            km = routes[0]["distanceMeters"] / 1000
            minutes = float(str(routes[0]["duration"]).rstrip("s")) / 60
            return Edge(a.id, b.id, "road", minutes, km * ROAD_INR_PER_KM, COMFORT["road"], ref=REF)
        return self.fallback.road_edge(a, b)


def default_road_provider() -> RoutesApiRoadProvider | HaversineRoadProvider:
    """Routes API when a key is configured, else the offline fake."""
    if os.environ.get("GOOGLE_MAPS_API_KEY"):
        return RoutesApiRoadProvider()
    return HaversineRoadProvider()
