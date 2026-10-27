"""Accounts without sign-in (HQ V3-AB): an anonymous per-browser id in the X-Client-Id header.

GET /me, PUT /me/consents, DELETE /me, GET /me/trips and POST /ratings use the shapes agreed with TY4
(Me, ConsentsUpdate, TripSummary, RatingIn). `client_id` is the only place that turns a request into a
uid, so Firebase ID-token verification can replace it later without touching the endpoints.
Postgres when DATABASE_URL is set (core/migrations), else in memory.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

from ty_contracts import Consents, ConsentsUpdate, Me, RatingIn, TripSummary

from .trips import MIGRATIONS, Trip, get_store

log = logging.getLogger(__name__)
router = APIRouter()

CLIENT_ID = re.compile(r"[A-Za-z0-9_-]{16,128}")


def client_id(x_client_id: str | None = Header(default=None)) -> str | None:
    """The caller's id, or None when the header is missing or malformed."""
    return x_client_id if x_client_id and CLIENT_ID.fullmatch(x_client_id) else None


def require_client(uid: str | None = Depends(client_id)) -> str:
    if uid is None:
        raise HTTPException(401, "send X-Client-Id: 16-128 characters of A-Z, a-z, 0-9, _ or -")
    return uid


@dataclass
class Rating:
    uid: str | None
    plan_id: str | None
    score: int
    comment: str | None
    lang: str


class AccountStore(Protocol):
    def consents(self, uid: str) -> tuple[Consents, datetime | None]: ...
    def set_consents(self, uid: str, update: ConsentsUpdate) -> tuple[Consents, datetime]: ...
    def add_rating(self, rating: Rating) -> None: ...
    def delete(self, uid: str) -> int: ...


class MemoryAccounts:
    def __init__(self) -> None:
        self._consents: dict[str, tuple[Consents, datetime]] = {}
        self.ratings: list[Rating] = []
        self._lock = threading.Lock()

    def consents(self, uid: str) -> tuple[Consents, datetime | None]:
        return self._consents.get(uid, (Consents(), None))

    def set_consents(self, uid: str, update: ConsentsUpdate) -> tuple[Consents, datetime]:
        with self._lock:
            now = datetime.now(UTC)
            merged = self.consents(uid)[0].model_copy(update=update.model_dump(exclude_none=True))
            self._consents[uid] = (merged, now)
            return merged, now

    def add_rating(self, rating: Rating) -> None:
        with self._lock:
            self.ratings.append(rating)

    def delete(self, uid: str) -> int:
        with self._lock:
            n = 1 if self._consents.pop(uid, None) else 0
            kept = [r for r in self.ratings if r.uid != uid]
            n += len(self.ratings) - len(kept)
            self.ratings = kept
            return n


class PgAccounts:
    def __init__(self, url: str) -> None:
        self.url = url
        with self._connect() as conn:
            for sql in sorted(MIGRATIONS.glob("*.sql")):
                conn.execute(sql.read_text(encoding="utf-8"))

    def _connect(self):
        import psycopg

        return psycopg.connect(self.url, autocommit=True, connect_timeout=5)

    def consents(self, uid: str) -> tuple[Consents, datetime | None]:
        with self._connect() as conn:
            row = conn.execute("SELECT plan_history, location, analytics, updated_at FROM consents WHERE uid = %s",
                               (uid,)).fetchone()
        if row is None:
            return Consents(), None
        return Consents(plan_history=row[0], location=row[1], analytics=row[2]), row[3]

    def set_consents(self, uid: str, update: ConsentsUpdate) -> tuple[Consents, datetime]:
        merged = self.consents(uid)[0].model_copy(update=update.model_dump(exclude_none=True))
        with self._connect() as conn:
            row = conn.execute(
                "INSERT INTO consents (uid, plan_history, location, analytics, updated_at) VALUES (%s, %s, %s, %s, now()) "
                "ON CONFLICT (uid) DO UPDATE SET plan_history = EXCLUDED.plan_history, location = EXCLUDED.location, "
                "analytics = EXCLUDED.analytics, updated_at = now() RETURNING updated_at",
                (uid, merged.plan_history, merged.location, merged.analytics),
            ).fetchone()
        return merged, row[0]

    def add_rating(self, rating: Rating) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO ratings (uid, plan_id, score, comment, lang) VALUES (%s, %s, %s, %s, %s)",
                         (rating.uid, rating.plan_id, rating.score, rating.comment, rating.lang))

    def delete(self, uid: str) -> int:
        with self._connect() as conn, conn.transaction():
            n = conn.execute("DELETE FROM consents WHERE uid = %s", (uid,)).rowcount
            return n + conn.execute("DELETE FROM ratings WHERE uid = %s", (uid,)).rowcount


_accounts: AccountStore | None = None


def get_accounts() -> AccountStore:
    global _accounts
    if _accounts is None:
        url = os.getenv("DATABASE_URL")
        _accounts = PgAccounts(url) if url else MemoryAccounts()
    return _accounts


def set_accounts(store: AccountStore | None) -> None:
    """Tests swap the store; None goes back to choosing from DATABASE_URL."""
    global _accounts
    _accounts = store


def keeps_history(uid: str | None) -> bool:
    """Plans are linked to an id only when it opted in to plan history."""
    return bool(uid) and get_accounts().consents(uid)[0].plan_history


def _me(uid: str) -> Me:
    consents, updated = get_accounts().consents(uid)
    return Me(uid=uid, consents=consents, consents_updated_at=updated)


def _summary(t: Trip) -> TripSummary:
    r = t.itinerary.request
    span = f"{r.start_date:%d %b}" if r.start_date == r.end_date else f"{r.start_date:%d %b} – {r.end_date:%d %b}"
    return TripSummary(plan_id=t.id, share_token=t.share_token, title=f"{', '.join(r.destinations)}, {span}",
                       origin=r.origin, destinations=r.destinations, start_date=r.start_date, end_date=r.end_date,
                       created_at=t.created_at)


# Store calls (Postgres) are blocking; the endpoints are plain `def`, so FastAPI runs them in its threadpool.


@router.get("/me", response_model=Me)
def me(uid: str = Depends(require_client)) -> Me:
    return _me(uid)


@router.put("/me/consents", response_model=Me)
def put_consents(body: ConsentsUpdate, uid: str = Depends(require_client)) -> Me:
    get_accounts().set_consents(uid, body)
    return _me(uid)


@router.delete("/me", status_code=202)
def delete_me(uid: str = Depends(require_client)) -> dict:
    """Everything for this id: its trips (their share links stop working), consents and ratings."""
    items = get_store().delete_owner(uid) + get_accounts().delete(uid)
    log.warning("deleted account data: %d items", items)  # no id in the log
    return {"deleted": True, "items": items}


@router.get("/me/trips", response_model=list[TripSummary])
def my_trips(uid: str = Depends(require_client)) -> list[TripSummary]:
    return [_summary(t) for t in get_store().by_owner(uid)]


@router.post("/ratings", status_code=201)
async def rate(body: RatingIn, uid: str | None = Depends(client_id)) -> JSONResponse:
    rating = Rating(uid, body.plan_id, body.score, body.comment, body.lang.value)
    await asyncio.to_thread(get_accounts().add_rating, rating)
    return JSONResponse({"ok": True}, status_code=201)
