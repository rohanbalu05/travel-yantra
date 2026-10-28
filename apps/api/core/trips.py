"""Trip storage (card #37): Postgres when DATABASE_URL is set, else in memory (lost on restart).

A trip id is the plan_id clients use for revise; the share token opens a read-only copy. A revise updates
the trip in place (same id and share token, version + 1), so one trip is one entry however often it changes.
Trips saved before that have a `revised_from` chain; only the newest of a chain is listed.
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
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
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: int = 1
    updated_at: datetime | None = None
    # A one-way key of the browser, chat or account that made the trip (accounts.creator_key), kept even without
    # the plan_history consent, so only its maker can change a trip that has no owner. None for older trips.
    creator: str | None = None

    @property
    def changed_at(self) -> datetime:
        return self.updated_at or self.created_at


def new_ids() -> tuple[str, str]:
    # The share token is a capability: unguessable, and separate from the id used for revise.
    return uuid.uuid4().hex, secrets.token_urlsafe(16)


class TripStore(Protocol):
    def save(self, itinerary: Itinerary, owner: str | None = None, revised_from: str | None = None,
             creator: str | None = None) -> Trip: ...
    def get(self, trip_id: str) -> Trip | None: ...
    def update(self, trip_id: str, itinerary: Itinerary, owner: str | None = None,
               version: int | None = None) -> Trip | None: ...
    def by_share_token(self, token: str) -> Trip | None: ...
    def by_owner(self, owner: str) -> list[Trip]: ...
    def delete_owner(self, owner: str) -> int: ...
    def delete_creator(self, creator: str) -> list[str]: ...
    def reassign_owner(self, old: str, new: str) -> int: ...
    def delete(self, trip_id: str) -> bool: ...


class TripChanged(Exception):
    """The trip got a newer version (another tab or channel) since this revise read it."""


class MemoryStore:
    def __init__(self, limit: int = MAX_MEMORY_TRIPS) -> None:
        self.limit = limit
        self._trips: OrderedDict[str, Trip] = OrderedDict()
        self._lock = threading.Lock()

    def save(self, itinerary: Itinerary, owner: str | None = None, revised_from: str | None = None,
             creator: str | None = None) -> Trip:
        trip_id, token = new_ids()
        trip = Trip(trip_id, token, itinerary.model_copy(deep=True), owner, revised_from, creator=creator)
        with self._lock:
            self._trips[trip_id] = trip
            while len(self._trips) > self.limit:
                self._trips.popitem(last=False)
        return trip

    def get(self, trip_id: str) -> Trip | None:
        return self._trips.get(trip_id)

    def update(self, trip_id: str, itinerary: Itinerary, owner: str | None = None,
               version: int | None = None) -> Trip | None:
        """A new version of the trip: same id and share token. `owner` claims a trip that has none. With
        `version`, TripChanged when the stored trip is no longer that version (no silent overwrite)."""
        with self._lock:
            old = self._trips.get(trip_id)
            if old is None:
                return None
            if version is not None and old.version != version:
                raise TripChanged(trip_id)
            trip = replace(old, itinerary=itinerary.model_copy(deep=True), owner=old.owner or owner,
                           version=old.version + 1, updated_at=datetime.now(UTC))
            self._trips[trip_id] = trip
            self._trips.move_to_end(trip_id)
            return trip

    def by_share_token(self, token: str) -> Trip | None:
        return next((t for t in list(self._trips.values()) if secrets.compare_digest(t.share_token, token)), None)

    def by_owner(self, owner: str) -> list[Trip]:
        """One per trip (the newest of an old revised_from chain), most recently changed first."""
        mine = [t for t in list(self._trips.values()) if t.owner == owner]
        superseded = {t.revised_from for t in mine}
        return sorted((t for t in mine if t.id not in superseded), key=lambda t: t.changed_at, reverse=True)

    def delete(self, trip_id: str) -> bool:
        with self._lock:
            return self._trips.pop(trip_id, None) is not None

    def reassign_owner(self, old: str, new: str) -> int:
        with self._lock:
            mine = [k for k, t in self._trips.items() if t.owner == old]
            for k in mine:
                t = self._trips[k]
                self._trips[k] = replace(t, owner=new)
            return len(mine)

    def delete_owner(self, owner: str) -> int:
        with self._lock:
            gone = [k for k, t in self._trips.items() if t.owner == owner]
            for k in gone:
                del self._trips[k]
        return len(gone)

    def delete_creator(self, creator: str) -> list[str]:
        """Trips with no owner that this maker made (DELETE /me). Returns their ids."""
        with self._lock:
            gone = [k for k, t in self._trips.items() if t.owner is None and t.creator == creator]
            for k in gone:
                del self._trips[k]
        return gone


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

    def save(self, itinerary: Itinerary, owner: str | None = None, revised_from: str | None = None,
             creator: str | None = None) -> Trip:
        trip_id, token = new_ids()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO trips (id, share_token, owner, revised_from, itinerary, creator) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, %s)",
                (trip_id, token, owner, revised_from, itinerary.model_dump_json(by_alias=True), creator),
            )
        return Trip(trip_id, token, itinerary, owner, revised_from, creator=creator)

    _COLUMNS = "id, share_token, itinerary, owner, revised_from, created_at, version, updated_at, creator"
    _SELECT = {
        "id": f"SELECT {_COLUMNS} FROM trips WHERE id = %s",
        "share_token": f"SELECT {_COLUMNS} FROM trips WHERE share_token = %s",
    }

    @staticmethod
    def _trip(row) -> Trip:
        return Trip(row[0], row[1], Itinerary.model_validate(row[2]), row[3], row[4], row[5], row[6], row[7], row[8])

    def _one(self, key: str, value: str) -> Trip | None:
        with self._connect() as conn:
            row = conn.execute(self._SELECT[key], (value,)).fetchone()
        return None if row is None else self._trip(row)

    def by_owner(self, owner: str) -> list[Trip]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {self._COLUMNS} FROM trips t WHERE owner = %s AND NOT EXISTS "
                "(SELECT 1 FROM trips n WHERE n.revised_from = t.id AND n.owner = t.owner) "
                "ORDER BY coalesce(updated_at, created_at) DESC", (owner,)).fetchall()
        return [self._trip(r) for r in rows]

    def delete(self, trip_id: str) -> bool:
        with self._connect() as conn, conn.transaction():
            conn.execute("UPDATE trips SET revised_from = NULL WHERE revised_from = %s", (trip_id,))
            return conn.execute("DELETE FROM trips WHERE id = %s", (trip_id,)).rowcount > 0

    def reassign_owner(self, old: str, new: str) -> int:
        with self._connect() as conn:
            return conn.execute("UPDATE trips SET owner = %s WHERE owner = %s", (new, old)).rowcount

    def delete_owner(self, owner: str) -> int:
        with self._connect() as conn, conn.transaction():
            # Revisions of these trips may belong to nobody; unlink them before the delete.
            conn.execute("UPDATE trips SET revised_from = NULL WHERE revised_from IN "
                         "(SELECT id FROM trips WHERE owner = %s)", (owner,))
            return conn.execute("DELETE FROM trips WHERE owner = %s", (owner,)).rowcount

    def delete_creator(self, creator: str) -> list[str]:
        with self._connect() as conn, conn.transaction():
            conn.execute("UPDATE trips SET revised_from = NULL WHERE revised_from IN "
                         "(SELECT id FROM trips WHERE owner IS NULL AND creator = %s)", (creator,))
            rows = conn.execute("DELETE FROM trips WHERE owner IS NULL AND creator = %s RETURNING id",
                                (creator,)).fetchall()
        return [r[0] for r in rows]

    def get(self, trip_id: str) -> Trip | None:
        return self._one("id", trip_id)

    def update(self, trip_id: str, itinerary: Itinerary, owner: str | None = None,
               version: int | None = None) -> Trip | None:
        with self._connect() as conn:
            row = conn.execute(
                f"UPDATE trips SET itinerary = %s::jsonb, owner = coalesce(owner, %s), version = version + 1, "
                f"updated_at = now() WHERE id = %s AND (%s::int IS NULL OR version = %s::int) RETURNING {self._COLUMNS}",
                (itinerary.model_dump_json(by_alias=True), owner, trip_id, version, version)).fetchone()
            if row is None and version is not None and conn.execute(
                    "SELECT 1 FROM trips WHERE id = %s", (trip_id,)).fetchone():
                raise TripChanged(trip_id)
        return None if row is None else self._trip(row)

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
