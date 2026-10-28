"""Conversation state: Postgres (table chat_conversations) when DATABASE_URL is set, else memory."""

from __future__ import annotations

import asyncio
import logging
import os
from collections import OrderedDict
from typing import Protocol

from .models import Conversation

log = logging.getLogger(__name__)
MAX_MEMORY = 2000
KEEP_DAYS = 30  # conversations untouched this long are deleted (the plans themselves stay)

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_conversations (
    id         text PRIMARY KEY,
    state      jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_conversations_updated_idx ON chat_conversations (updated_at);
"""


class Store(Protocol):
    async def get(self, cid: str) -> Conversation | None: ...
    async def put(self, cid: str, conv: Conversation) -> None: ...
    async def delete(self, cid: str) -> None: ...


class MemoryStore:
    """Lost on restart; for tests and local runs without a database."""

    def __init__(self, limit: int = MAX_MEMORY) -> None:
        self.limit = limit
        self.rows: OrderedDict[str, str] = OrderedDict()

    async def get(self, cid: str) -> Conversation | None:
        raw = self.rows.get(cid)
        return None if raw is None else Conversation.model_validate_json(raw)

    async def put(self, cid: str, conv: Conversation) -> None:
        self.rows[cid] = conv.model_dump_json()
        self.rows.move_to_end(cid)
        while len(self.rows) > self.limit:
            self.rows.popitem(last=False)

    async def delete(self, cid: str) -> None:
        self.rows.pop(cid, None)


class PgStore:
    """One short-lived connection per call, as core.trips does; the table is created on first use."""

    def __init__(self, url: str) -> None:
        self.url = url
        self._ready = False

    def _connect(self):
        import psycopg

        return psycopg.connect(self.url, autocommit=True, connect_timeout=5)

    def _setup(self, conn) -> None:
        if not self._ready:
            conn.execute(SCHEMA)
            gone = conn.execute(
                "DELETE FROM chat_conversations WHERE updated_at < now() - make_interval(days => %s)",
                (KEEP_DAYS,),
            ).rowcount
            log.info("chat store ready; %d old conversations deleted", gone)
            self._ready = True

    def _get(self, cid: str) -> Conversation | None:
        with self._connect() as conn:
            self._setup(conn)
            row = conn.execute(
                "SELECT state FROM chat_conversations WHERE id = %s", (cid,)
            ).fetchone()
        return None if row is None else Conversation.model_validate(row[0])

    def _put(self, cid: str, conv: Conversation) -> None:
        with self._connect() as conn:
            self._setup(conn)
            conn.execute(
                "INSERT INTO chat_conversations (id, state, updated_at) VALUES (%s, %s::jsonb, now())"
                " ON CONFLICT (id) DO UPDATE SET state = EXCLUDED.state, updated_at = now()",
                (cid, conv.model_dump_json()),
            )

    def _delete(self, cid: str) -> None:
        with self._connect() as conn:
            self._setup(conn)
            conn.execute("DELETE FROM chat_conversations WHERE id = %s", (cid,))

    async def get(self, cid: str) -> Conversation | None:
        return await asyncio.to_thread(self._get, cid)

    async def put(self, cid: str, conv: Conversation) -> None:
        await asyncio.to_thread(self._put, cid, conv)

    async def delete(self, cid: str) -> None:
        await asyncio.to_thread(self._delete, cid)


_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        url = os.getenv("DATABASE_URL")
        _store = PgStore(url) if url else MemoryStore()
        log.info("chat store: %s", type(_store).__name__)
    return _store


def set_store(store: Store | None) -> None:
    """Tests swap the store; None goes back to choosing from DATABASE_URL."""
    global _store
    _store = store
