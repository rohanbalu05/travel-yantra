"""Trip storage (card #37): Postgres when DATABASE_URL is set, else in memory (lost on restart).

A trip id is the plan_id clients use for revise; the share token opens a read-only copy.
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ty_contracts import Itinerary

log = logging.getLogger(__name__)

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
MAX_MEMORY_TRIPS = 500


@dataclass(frozen=True)
class Trip:
    id: str
    share_token: str
    itinerary: Itinerary
    owner: str | None = None
    revised_from: str | None = None


def new_ids() -> tuple[str, str]:
    # The share token is a capability: unguessable, and separate from the id used for revise.
    return uuid.uuid4().hex, secrets.token_urlsafe(16)


class TripStore(Protocol):
    def save(self, itinerary: Itinerary, owner: str | None = None, revised_from: str | None = None) -> Trip: ...
    def get(self, trip_id: str) -> Trip | None: ...
    def by_share_token(self, token: str) -> Trip | None: ...


class MemoryStore:
    def __init__(self, limit: int = MAX_MEMORY_TRIPS) -> None:
        self.limit = limit
        self._trips: OrderedDict[str, Trip] = OrderedDict()
        self._lock = threading.Lock()

    def save(self, itinerary: Itinerary, owner: str | None = None, revised_from: str | None = None) -> Trip:
        trip_id, token = new_ids()
        trip = Trip(trip_id, token, itinerary.model_copy(deep=True), owner, revised_from)
        with self._lock:
            self._trips[trip_id] = trip
            while len(self._trips) > self.limit:
                self._trips.popitem(last=False)
        return trip

    def get(self, trip_id: str) -> Trip | None:
        return self._trips.get(trip_id)

    def by_share_token(self, token: str) -> Trip | None:
        return next((t for t in list(self._trips.values()) if secrets.compare_digest(t.share_token, token)), None)


class PgStore:
    """One short-lived connection per call; Cloud Run scales to zero, so no pool to keep warm."""

    def __init__(self, url: str) -> None:
        self.url = url
        with self._connect() as conn:
            for sql in sorted(MIGRATIONS.glob("*.sql")):
                conn.execute(sql.read_text(encoding="utf-8"))

    def _connect(self):
        import psycopg

        return psycopg.connect(self.url, autocommit=True, connect_timeout=5)

    def save(self, itinerary: Itinerary, owner: str | None = None, revised_from: str | None = None) -> Trip:
        trip_id, token = new_ids()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO trips (id, share_token, owner, revised_from, itinerary) VALUES (%s, %s, %s, %s, %s::jsonb)",
                (trip_id, token, owner, revised_from, itinerary.model_dump_json(by_alias=True)),
            )
        return Trip(trip_id, token, itinerary, owner, revised_from)

    _SELECT = {
        "id": "SELECT id, share_token, itinerary, owner, revised_from FROM trips WHERE id = %s",
        "share_token": "SELECT id, share_token, itinerary, owner, revised_from FROM trips WHERE share_token = %s",
    }

    def _one(self, key: str, value: str) -> Trip | None:
        with self._connect() as conn:
            row = conn.execute(self._SELECT[key], (value,)).fetchone()
        if row is None:
            return None
        return Trip(row[0], row[1], Itinerary.model_validate(row[2]), row[3], row[4])

    def get(self, trip_id: str) -> Trip | None:
        return self._one("id", trip_id)

    def by_share_token(self, token: str) -> Trip | None:
        return self._one("share_token", token)


_store: TripStore | None = None


def get_store() -> TripStore:
    global _store
    if _store is None:
        url = os.getenv("DATABASE_URL")
        _store = PgStore(url) if url else MemoryStore()
        log.info("trips store: %s", type(_store).__name__)
    return _store


def set_store(store: TripStore | None) -> None:
    """Tests swap the store; None goes back to choosing from DATABASE_URL."""
    global _store
    _store = store
