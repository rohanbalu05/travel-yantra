"""Accounts without sign-in (HQ V3-AB): an anonymous per-browser id in the X-Client-Id header.

GET /me, PUT /me/consents, DELETE /me, GET /me/trips and POST /ratings use the shapes agreed with TY4
(Me, ConsentsUpdate, TripSummary, RatingIn). `client_id` is the only place that turns a request into a
uid, so Firebase ID-token verification can replace it later without touching the endpoints.
Postgres when DATABASE_URL is set (core/migrations), else in memory.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

from ty_contracts import (
    Consents,
    ConsentsUpdate,
    Itinerary,
    Me,
    Mode,
    RatingIn,
    TripSummary,
)

from . import auth
from .trips import MIGRATIONS, Trip, get_store

log = logging.getLogger(__name__)
router = APIRouter()

CLIENT_ID = re.compile(r"[A-Za-z0-9_-]{16,128}")


@dataclass(frozen=True)
class Identity:
    uid: str
    email: str | None = None
    name: str | None = None


def identity(authorization: str | None = Header(default=None),
             x_client_id: str | None = Header(default=None)) -> Identity | None:
    """Who is calling. A Firebase ID token (Authorization: Bearer) means a signed-in account; a bad token is a
    401, never a silent fall-back. Without one, the anonymous X-Client-Id (or nobody). On a signed-in call that
    also carries the browser's X-Client-Id, that browser's anonymous data moves to the account, once."""
    anon = x_client_id if x_client_id and CLIENT_ID.fullmatch(x_client_id) else None
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "send Authorization: Bearer <Firebase ID token>")
        try:
            claims = auth.verify(token.strip())
        except auth.AuthError as exc:
            raise HTTPException(401, str(exc)) from exc
        except auth.AuthUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        if anon:
            link_browser(anon, claims.uid)
        return Identity(claims.uid, claims.email, claims.name)
    return Identity(anon) if anon else None


def creator_key(cid: str) -> str:
    """A one-way key for a trip's maker: the trip store never holds the browser, chat or account id itself."""
    return hashlib.sha256(f"ty-creator:{cid}".encode()).hexdigest()[:32]


def caller_ids(who: Identity | None = Depends(identity), x_client_id: str | None = Header(default=None)) -> tuple[str, ...]:
    """Every id the caller speaks for: the account (or browser) id, and the browser id sent with a sign-in."""
    ids = [who.uid] if who else []
    if x_client_id and CLIENT_ID.fullmatch(x_client_id) and x_client_id not in ids:
        ids.append(x_client_id)
    return tuple(ids)


def client_id(who: Identity | None = Depends(identity)) -> str | None:
    """The caller's uid (an account or an anonymous browser id), or None."""
    return who.uid if who else None


def require_identity(who: Identity | None = Depends(identity)) -> Identity:
    if who is None:
        raise HTTPException(401, "sign in, or send X-Client-Id: 16-128 characters of A-Z, a-z, 0-9, _ or -")
    return who


def require_client(who: Identity = Depends(require_identity)) -> str:
    return who.uid


def link_browser(anon: str, uid: str) -> None:
    """First sign-in from a browser: its anonymous trips, ratings and consents become the account's. Runs
    once per browser id (recorded); later calls are a cheap lookup."""
    accounts = get_accounts()
    if accounts.linked(anon):
        if not accounts.pending(anon, uid):
            return
        moved = 0  # claimed earlier by this account, but its trips did not move: try again
    else:
        # Claim the browser first: if two accounts race, only the one whose claim lands moves the trips.
        moved = accounts.link(anon, uid)
        if moved is None:
            return
    try:
        moved += get_store().reassign_owner(anon, uid)
    except Exception:
        log.exception("moving a browser's trips failed; will retry on its next signed-in call")
        return
    accounts.mark_moved(anon)
    log.warning("linked a browser to an account: %d items moved", moved)  # no ids in the log


def default_consents(uid: str) -> Consents:
    """Before any choice: a signed-in account keeps its plan history (that is why people sign in; they can
    turn it off); an anonymous browser keeps nothing."""
    return Consents(plan_history=uid.startswith(auth.ACCOUNT_PREFIX))


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
    def delete(self, uid: str, plan_ids: list[str] | None = None) -> int: ...
    def linked(self, anon: str) -> bool: ...
    def pending(self, anon: str, uid: str) -> bool: ...
    def mark_moved(self, anon: str) -> None: ...
    def delete_ratings_for(self, plan_ids: list[str]) -> int: ...
    def link(self, anon: str, uid: str) -> int | None: ...


class MemoryAccounts:
    def __init__(self) -> None:
        self._consents: dict[str, tuple[Consents, datetime]] = {}
        self.ratings: list[Rating] = []
        self._links: dict[str, str] = {}
        self._unmoved: set[str] = set()
        self._lock = threading.Lock()

    def consents(self, uid: str) -> tuple[Consents, datetime | None]:
        return self._consents.get(uid, (default_consents(uid), None))

    def set_consents(self, uid: str, update: ConsentsUpdate) -> tuple[Consents, datetime]:
        with self._lock:
            now = datetime.now(UTC)
            merged = self.consents(uid)[0].model_copy(update=update.model_dump(exclude_none=True))
            self._consents[uid] = (merged, now)
            return merged, now

    def add_rating(self, rating: Rating) -> None:
        with self._lock:
            self.ratings.append(rating)

    def delete(self, uid: str, plan_ids: list[str] | None = None) -> int:
        """The id's consents and ratings, plus any rating (even anonymous) of one of its plans."""
        plans = set(plan_ids or [])
        with self._lock:
            self._links = {a: u for a, u in self._links.items() if u != uid}
            n = 1 if self._consents.pop(uid, None) else 0
            kept = [r for r in self.ratings if r.uid != uid and r.plan_id not in plans]
            n += len(self.ratings) - len(kept)
            self.ratings = kept
            return n


    def linked(self, anon: str) -> bool:
        return anon in self._links

    def pending(self, anon: str, uid: str) -> bool:
        return self._links.get(anon) == uid and anon in self._unmoved

    def mark_moved(self, anon: str) -> None:
        self._unmoved.discard(anon)

    def delete_ratings_for(self, plan_ids: list[str]) -> int:
        gone = set(plan_ids)
        with self._lock:
            kept = [r for r in self.ratings if r.plan_id not in gone]
            n, self.ratings = len(self.ratings) - len(kept), kept
            return n

    def link(self, anon: str, uid: str) -> int | None:
        """Claim the browser for the account and move its ratings and (if the account has none yet) consents.
        None when another account claimed it first."""
        with self._lock:
            if anon in self._links:
                return None
            self._links[anon] = uid
            self._unmoved.add(anon)
            n = 0
            for r in self.ratings:
                if r.uid == anon:
                    r.uid, n = uid, n + 1
            browser = self._consents.pop(anon, None)
            if browser and uid not in self._consents:
                self._consents[uid] = browser
                n += 1
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
            return default_consents(uid), None
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

    def delete(self, uid: str, plan_ids: list[str] | None = None) -> int:
        with self._connect() as conn, conn.transaction():
            conn.execute("DELETE FROM account_links WHERE uid = %s", (uid,))
            n = conn.execute("DELETE FROM consents WHERE uid = %s", (uid,)).rowcount
            return n + conn.execute("DELETE FROM ratings WHERE uid = %s OR plan_id = ANY(%s)",
                                    (uid, list(plan_ids or []))).rowcount


    def delete_ratings_for(self, plan_ids: list[str]) -> int:
        with self._connect() as conn:
            return conn.execute("DELETE FROM ratings WHERE plan_id = ANY(%s)", (list(plan_ids),)).rowcount

    def pending(self, anon: str, uid: str) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM account_links WHERE anon_id = %s AND uid = %s AND NOT moved",
                                (anon, uid)).fetchone() is not None

    def mark_moved(self, anon: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE account_links SET moved = true WHERE anon_id = %s", (anon,))

    def linked(self, anon: str) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM account_links WHERE anon_id = %s", (anon,)).fetchone() is not None

    def link(self, anon: str, uid: str) -> int | None:
        with self._connect() as conn, conn.transaction():
            if conn.execute("INSERT INTO account_links (anon_id, uid, moved) VALUES (%s, %s, false) "
                            "ON CONFLICT DO NOTHING", (anon, uid)).rowcount == 0:
                return None  # another request claimed it first
            n = conn.execute("UPDATE ratings SET uid = %s WHERE uid = %s", (uid, anon)).rowcount
            # The account keeps its own choices if it has any; else it takes the browser's.
            n += conn.execute("INSERT INTO consents (uid, plan_history, location, analytics, updated_at) "
                              "SELECT %s, plan_history, location, analytics, updated_at FROM consents WHERE uid = %s "
                              "ON CONFLICT (uid) DO NOTHING", (uid, anon)).rowcount
            conn.execute("DELETE FROM consents WHERE uid = %s", (anon,))
            return n


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


def _me(who: Identity) -> Me:
    consents, updated = get_accounts().consents(who.uid)
    return Me(uid=who.uid, email=who.email, name=who.name, consents=consents, consents_updated_at=updated)


def plan_mode(it: Itinerary) -> Mode | None:
    """The chosen mode, else the outbound journey's."""
    if it.request.transport_mode:
        return it.request.transport_mode
    return next((leg.mode for d in it.days for leg in d.legs if leg.role == "outbound"), None)


def _summary(t: Trip) -> TripSummary:
    from .checker import settled

    it = settled(t.itinerary)
    r = it.request
    span = f"{r.start_date:%d %b}" if r.start_date == r.end_date else f"{r.start_date:%d %b} – {r.end_date:%d %b}"
    return TripSummary(plan_id=t.id, share_token=t.share_token, title=f"{', '.join(r.destinations)}, {span}",
                       origin=r.origin, destinations=r.destinations, start_date=r.start_date, end_date=r.end_date,
                       created_at=t.created_at, updated_at=t.changed_at, mode=plan_mode(it),
                       travellers=max(len(r.constraints.travellers), 1), total_inr=it.budget.total_inr)


# Store calls (Postgres) are blocking; the endpoints are plain `def`, so FastAPI runs them in its threadpool.


@router.get("/me", response_model=Me)
def me(who: Identity = Depends(require_identity)) -> Me:
    return _me(who)


@router.put("/me/consents", response_model=Me)
def put_consents(body: ConsentsUpdate, who: Identity = Depends(require_identity)) -> Me:
    """Turning plan_history off also deletes the trips kept under it (their share links stop working)."""
    get_accounts().set_consents(who.uid, body)
    if body.plan_history is False:
        removed = get_store().delete_owner(who.uid)
        log.warning("plan_history withdrawn: %d trips deleted", removed)  # no id in the log
    return _me(who)


@router.delete("/me", status_code=202)
def delete_me(uid: str = Depends(require_client), ids: tuple[str, ...] = Depends(caller_ids)) -> dict:
    """Everything for this id: its trips (their share links stop working), consents and ratings."""
    plan_ids = [t.id for t in get_store().by_owner(uid)]
    # Its own trips, and the ones made without keeping a history (no owner) under any id it speaks for: the
    # account and the browser it signed in from. Ratings of all of them go too.
    made = [pid for c in dict.fromkeys((uid, *ids)) for pid in get_store().delete_creator(creator_key(c))]
    items = get_store().delete_owner(uid) + len(made) + get_accounts().delete(uid, plan_ids + made)
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

