"""Planning-time measurement for the user study: anonymous time-on-task events
(start, plan shown, booking chosen) per session, and median times per task and
arm. Session ids are random strings from the browser; no personal data.

Stored in Postgres (table routes_metric_events) when DATABASE_URL is set,
otherwise in memory (lost on restart; fine for local runs and tests)."""
from __future__ import annotations

import datetime as dt
import os
import re
import statistics
import threading
from collections import defaultdict, deque
from functools import lru_cache
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

Arm = Literal["ty", "baseline"]
EventName = Literal["start", "plan_shown", "booking_chosen"]
MAX_BODY_BYTES = 2048
MAX_MEMORY_ROWS = 50_000  # oldest dropped first; keeps an unauthenticated endpoint bounded
_PHONE_LIKE = re.compile(r"^\+?\d{10,}$")


class MetricEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")
    task: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    arm: Arm
    event: EventName
    at: dt.datetime | None = None

    @field_validator("session_id")
    @classmethod
    def _not_a_phone(cls, v: str) -> str:
        if _PHONE_LIKE.match(v.replace("-", "")):
            raise ValueError("session_id must be a random id, not a phone number")
        return v

    @field_validator("at")
    @classmethod
    def _aware(cls, v: dt.datetime | None) -> dt.datetime | None:
        return v.replace(tzinfo=dt.UTC) if v is not None and v.tzinfo is None else v


class TaskSummary(BaseModel):
    task: str
    arm: Arm
    sessions: int
    median_s_to_plan: float | None
    median_s_to_booking: float | None


class Store(Protocol):
    def add(self, e: MetricEvent) -> None: ...
    def all(self) -> list[MetricEvent]: ...


class MemoryStore:
    def __init__(self, max_rows: int = MAX_MEMORY_ROWS) -> None:
        self._rows: deque[MetricEvent] = deque(maxlen=max_rows)
        self._lock = threading.Lock()

    def add(self, e: MetricEvent) -> None:
        with self._lock:
            self._rows.append(e)

    def all(self) -> list[MetricEvent]:
        with self._lock:
            return list(self._rows)


DDL = """create table if not exists routes_metric_events (
    id bigserial primary key,
    session_id text not null,
    task text not null,
    arm text not null,
    event text not null,
    at timestamptz not null,
    received_at timestamptz not null default now()
)"""


class PgStore:
    def __init__(self, url: str) -> None:
        self._url = url
        self._ready = False

    def _conn(self):
        import psycopg

        conn = psycopg.connect(self._url, autocommit=True, connect_timeout=5)
        if not self._ready:
            conn.execute(DDL)
            self._ready = True
        return conn

    def add(self, e: MetricEvent) -> None:
        with self._conn() as conn:
            conn.execute("insert into routes_metric_events (session_id, task, arm, event, at)"
                         " values (%s, %s, %s, %s, %s)", (e.session_id, e.task, e.arm, e.event, e.at))

    def all(self) -> list[MetricEvent]:
        with self._conn() as conn:
            rows = conn.execute("select session_id, task, arm, event, at from routes_metric_events").fetchall()
        return [MetricEvent(session_id=s, task=t, arm=a, event=ev, at=at) for s, t, a, ev, at in rows]


def record(store: Store, e: MetricEvent, now: dt.datetime | None = None) -> MetricEvent:
    e = e.model_copy(update={"at": e.at or now or dt.datetime.now(dt.UTC)})
    store.add(e)
    return e


def summarise(events: list[MetricEvent]) -> list[TaskSummary]:
    """Per (task, arm): median seconds from a session's first start to its first
    plan_shown and to its first booking_chosen. Sessions without start are skipped."""
    first: dict[tuple[str, str, str], dict[str, dt.datetime]] = defaultdict(dict)
    for e in events:
        seen = first[(e.task, e.arm, e.session_id)]
        if e.event not in seen or e.at < seen[e.event]:
            seen[e.event] = e.at
    groups: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: {"n": [], "plan": [], "book": []})
    for (task, arm, _), seen in first.items():
        if "start" not in seen:
            continue
        g = groups[(task, arm)]
        g["n"].append(1)
        for key, ev in (("plan", "plan_shown"), ("book", "booking_chosen")):
            if ev in seen and seen[ev] >= seen["start"]:
                g[key].append((seen[ev] - seen["start"]).total_seconds())
    return [TaskSummary(task=task, arm=arm, sessions=len(g["n"]),
                        median_s_to_plan=statistics.median(g["plan"]) if g["plan"] else None,
                        median_s_to_booking=statistics.median(g["book"]) if g["book"] else None)
            for (task, arm), g in sorted(groups.items())]


@lru_cache(maxsize=1)
def get_store() -> Store:
    url = os.environ.get("DATABASE_URL")
    return PgStore(url) if url else MemoryStore()
