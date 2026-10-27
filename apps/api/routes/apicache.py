"""Shared response cache and live-call counter for the paid or capped APIs
(SerpApi, Routes API). One store for every instance: Postgres (tables
routes_api_cache and routes_api_calls, created if missing) when DATABASE_URL
is set, else a local JSON file (ROUTES_CACHE_FILE, default in the temp dir).

Counters are per (provider, period): `spend` adds one call only while the
count is under the cap, so two instances can never pass the cap between them
on Postgres. Cached payloads stay readable after they expire (`stale=True`),
so a capped provider can serve the last answer instead of going live."""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import threading
from functools import lru_cache
from pathlib import Path
from typing import Protocol

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def day_period(now: dt.datetime | None = None) -> str:
    return (now or dt.datetime.now(IST)).astimezone(IST).strftime("%Y-%m-%d")


def month_period(now: dt.datetime | None = None) -> str:
    return (now or dt.datetime.now(IST)).astimezone(IST).strftime("%Y-%m")


class Store(Protocol):
    def get(self, key: str, stale: bool = False) -> dict | None: ...
    def set(self, key: str, payload: dict, ttl_s: int) -> None: ...
    def spend(self, provider: str, period: str, cap: int) -> bool: ...
    def count(self, provider: str, period: str) -> int: ...


def _now() -> float:
    return dt.datetime.now(dt.UTC).timestamp()


class MemoryStore:
    """Per process; for tests and as the base of FileStore."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[dict, float]] = {}
        self._calls: dict[str, int] = {}
        self._lock = threading.Lock()

    def get(self, key, stale=False):
        with self._lock:
            hit = self._cache.get(key)
        if hit is None or (not stale and hit[1] <= _now()):
            return None
        return hit[0]

    def set(self, key, payload, ttl_s):
        with self._lock:
            self._cache[key] = (payload, _now() + ttl_s)
            self._saved()

    def spend(self, provider, period, cap):
        k = f"{provider}|{period}"
        with self._lock:
            if self._calls.get(k, 0) >= cap:
                return False
            self._calls[k] = self._calls.get(k, 0) + 1
            self._saved()
            return True

    def count(self, provider, period):
        with self._lock:
            return self._calls.get(f"{provider}|{period}", 0)

    def _saved(self) -> None:  # FileStore writes through; called with the lock held
        pass


class FileStore(MemoryStore):
    """A JSON file shared by the processes on one machine (local runs, scripts).
    Reloaded before each counter spend so two local processes see each other's calls."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self._cache = {k: (v[0], v[1]) for k, v in raw.get("cache", {}).items()}
        self._calls = dict(raw.get("calls", {}))

    def spend(self, provider, period, cap):
        with self._lock:
            self._load()
        return super().spend(provider, period, cap)

    def _saved(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"cache": self._cache, "calls": self._calls}), encoding="utf-8")
        os.replace(tmp, self.path)


DDL = (
    """create table if not exists routes_api_cache (
        key text primary key,
        payload jsonb not null,
        expires_at timestamptz not null,
        saved_at timestamptz not null default now()
    )""",
    """create table if not exists routes_api_calls (
        provider text not null,
        period text not null,
        n integer not null,
        primary key (provider, period)
    )""",
)


class PgStore:
    def __init__(self, url: str) -> None:
        self._url = url
        self._ready = False

    def _conn(self):
        import psycopg

        conn = psycopg.connect(self._url, autocommit=True, connect_timeout=5)
        if not self._ready:
            for stmt in DDL:
                conn.execute(stmt)
            self._ready = True
        return conn

    def get(self, key, stale=False):
        q = "select payload from routes_api_cache where key = %s"
        if not stale:
            q += " and expires_at > now()"
        with self._conn() as conn:
            row = conn.execute(q, (key,)).fetchone()
        return row[0] if row else None

    def set(self, key, payload, ttl_s):
        from psycopg.types.json import Jsonb

        with self._conn() as conn:
            conn.execute(
                "insert into routes_api_cache (key, payload, expires_at)"
                " values (%s, %s, now() + make_interval(secs => %s))"
                " on conflict (key) do update set payload = excluded.payload,"
                " expires_at = excluded.expires_at, saved_at = now()",
                (key, Jsonb(payload), ttl_s))

    def spend(self, provider, period, cap):
        if cap < 1:
            return False
        with self._conn() as conn:
            row = conn.execute(
                "insert into routes_api_calls (provider, period, n) values (%s, %s, 1)"
                " on conflict (provider, period) do update set n = routes_api_calls.n + 1"
                " where routes_api_calls.n < %s returning n",
                (provider, period, cap)).fetchone()
        return row is not None

    def count(self, provider, period):
        with self._conn() as conn:
            row = conn.execute("select n from routes_api_calls where provider = %s and period = %s",
                               (provider, period)).fetchone()
        return row[0] if row else 0


def default_file() -> Path:
    return Path(os.environ.get("ROUTES_CACHE_FILE") or Path(tempfile.gettempdir()) / "travel-yantra" / "routes-cache.json")


@lru_cache(maxsize=1)
def get_store() -> Store:
    url = os.environ.get("DATABASE_URL")
    return PgStore(url) if url else FileStore(default_file())
