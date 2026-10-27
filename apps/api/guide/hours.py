"""Opening hours from Google Places at runtime, for corpus places that carry a place_id.

The repo keeps only Places' place_id (Places terms, V3-AD); the hours themselves
are fetched when a trip needs them, through the cached and counted PlacesClient,
and live privately in Cloud SQL (places_cache, 7 days). Nothing here runs unless
the caller asks: planner.places_for stays offline.

    places = live_hours(places_for("Goa"))   # TY1's steps, after places_for

Without DATABASE_URL (no private cache) or GOOGLE_MAPS_API_KEY it fetches nothing
and returns the places unchanged. At most DAILY_CAP live calls a day per instance.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ty_contracts import Place

from .places import PgCache, PlacesClient
from .planner import place_ids

log = logging.getLogger(__name__)
DAILY_CAP = 300  # Enterprise Details is free to 1,000 a month; the 7-day cache keeps reuse cheap
WORKERS = 6
_spent: dict[str, int] = {}  # UTC date -> live calls this instance made


def _budget_left(today: str) -> int:
    return DAILY_CAP - _spent.get(today, 0)


def live_hours(
    places: list[Place],
    client: PlacesClient | None = None,
    *,
    connect: Callable[[], Any] | None = None,
) -> list[Place]:
    """The places, with opening_hours from Places where the corpus has a place_id and
    Places has hours. Any failure leaves that place as it was (hours unknown)."""
    ids = place_ids()
    todo = [(i, ids[p.id]) for i, p in enumerate(places) if p.id in ids and not p.opening_hours]
    if not todo:
        return places
    conn = None
    if client is None:
        if not os.environ.get("DATABASE_URL") or not os.environ.get("GOOGLE_MAPS_API_KEY"):
            return places
        conn = (connect or _connect)()
        client = PlacesClient(cache=PgCache(conn))
    today = time.strftime("%Y-%m-%d", time.gmtime())
    todo = todo[: max(_budget_left(today), 0)]  # worst case every one is a cache miss
    out, start = list(places), client.calls

    def one(item: tuple[int, str]):
        i, pid = item
        try:
            return i, client.hours(pid)
        except Exception:  # timeout, quota, a place Places dropped: hours stay unknown
            log.warning("places hours failed for %s", places[i].id, exc_info=True)
            return i, []

    try:
        # psycopg 3 connections are thread-safe: cache reads queue, the HTTP calls overlap.
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for i, hours in pool.map(one, todo):
                if hours:
                    out[i] = out[i].model_copy(update={"opening_hours": hours})
    finally:
        _spent[today] = _spent.get(today, 0) + client.calls - start
        if conn is not None:
            conn.close()
    return out


def _connect():
    import psycopg

    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, connect_timeout=5)
