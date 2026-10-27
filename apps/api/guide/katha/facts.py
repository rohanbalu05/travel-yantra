"""Step 1 of the pipeline: the sourced facts a story may use, numbered.

Facts come only from the corpus (doc_chunk). A story may cite them as [n] and
may not say anything they do not carry. Thin sources make a shorter story.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .. import names
from ..planner import _slug, corpus_city

#: How many facts each length may draw on, and how many it needs.
CAP = {2: 8, 5: 14, 10: 24}
NEED = {2: 2, 5: 6, 10: 12}
PER_DAY_STOP = 3

COLS = "id, poi_id, city, title, body, is_legend, source_name, source_url"
#: Story material first. Practical notes (tickets, water) never make a story.
STORY_ORDER = """CASE chunk_type WHEN 'hook' THEN 0 WHEN 'story' THEN 1 WHEN 'sensory' THEN 2
    WHEN 'fact' THEN 3 ELSE 4 END"""


FIELD_NOTES = "Travel Yantra field notes"
OUR_NOTES = {"travel-yantra field notes", "travel yantra field notes", "travel yantra"}


class Fact(BaseModel):
    n: int
    chunk_id: int
    city: str | None
    title: str | None
    body: str
    is_legend: bool
    source_name: str | None
    source_url: str | None

    @property
    def source(self) -> str:
        """What the reader sees in the source list (HQ QA): a web source is its link; any
        other is named honestly, without a link: our own notes as "Travel Yantra field
        notes", the rest by their original source name."""
        if self.source_url:
            return self.source_url
        name = (self.source_name or "").strip()
        return FIELD_NOTES if not name or name.lower() in OUR_NOTES else name


class Subject(BaseModel):
    kind: str
    name: str  # the place or city as the corpus names it, or the day's label
    city: str | None = None
    poi_ids: list[int] = []


class UnknownSubject(LookupError):
    pass


def _poi_by_name_or_slug(db: Any, key: str) -> tuple[int, str, str] | None:
    """The poi a traveller means: exact name, planner slug or Kannada name; then the same
    after normalizing (case, punctuation, "story of", Mysore/Mysuru, Hindi and Kannada demo
    names); then a prefix ("Vittala Temple" for "... and Stone Chariot"); then difflib with
    one clear winner. WA-11, WA-12: "story mysuru palace" used to 404."""
    rows = [r[:4] for r in db.execute("SELECT id, name, city, name_kn FROM poi").fetchall()]
    k = key.strip().lower()
    for pid, name, city, _ in rows:  # 130 rows: a scan is simpler than a slug column
        if k in (name.lower(), _slug(f"{city} {name}")):
            return pid, name, city
    n = names.normalize(key)
    if not n:
        return None
    by_norm = {}
    for pid, name, city, kn in rows:
        for form in (name, kn):
            if form:
                by_norm.setdefault(names.normalize(form), (pid, name, city))
    if n in by_norm:
        return by_norm[n]
    prefixed = [r for norm, r in by_norm.items() if norm.startswith(n + " ")]
    if len({r[0] for r in prefixed}) == 1:
        return prefixed[0]
    if hit := names.best(key, [name for _, name, _, _ in rows]):
        return next((pid, name, city) for pid, name, city, _ in rows if name == hit)
    return None


def resolve(db: Any, kind: str, subject: str, places: list[str] = ()) -> Subject:
    if kind == "place":
        if not (hit := _poi_by_name_or_slug(db, subject)):
            raise UnknownSubject(subject)
        return Subject(kind=kind, name=hit[1], city=hit[2], poi_ids=[hit[0]])
    if kind == "city":
        if not (city := corpus_city(subject)):
            raise UnknownSubject(subject)
        return Subject(kind=kind, name=city, city=city)
    found = [p for p in (_poi_by_name_or_slug(db, s) for s in places) if p]
    if not found:
        raise UnknownSubject(subject)
    return Subject(kind=kind, name=subject, city=found[0][2], poi_ids=[p[0] for p in found])


def _rows(db: Any, where: str, params: tuple, limit: int) -> list[tuple]:
    return db.execute(
        f"SELECT {COLS} FROM doc_chunk WHERE NOT retired AND chunk_type <> 'practical' "
        f"AND {where} ORDER BY coalesce(tier, 2), {STORY_ORDER}, id LIMIT %s",
        (*params, limit),
    ).fetchall()


def gather(db: Any, subject: Subject, length_min: int) -> list[Fact]:
    cap = CAP[length_min]
    if subject.kind == "place":
        rows = _rows(db, "poi_id = %s", (subject.poi_ids[0],), cap)
        # Room left: what the city layer says, for context around the place.
        rows += _rows(db, "poi_id IS NULL AND city = %s AND coalesce(tier, 2) <= %s",
                      (subject.city, length_min), max(cap - len(rows), 0) // 2)  # fmt: skip
    elif subject.kind == "city":
        rows = _rows(db, "poi_id IS NULL AND city = %s AND coalesce(tier, 2) <= %s",
                     (subject.city, length_min), cap)  # fmt: skip
        if len(rows) < cap:  # then the city's best-known places
            rows += db.execute(
                f"SELECT {', '.join('c.' + c.strip() for c in COLS.split(','))} "
                "FROM doc_chunk c JOIN poi p ON p.id = c.poi_id "
                f"WHERE NOT c.retired AND c.chunk_type <> 'practical' AND c.city = %s "
                f"ORDER BY p.popularity DESC NULLS LAST, {STORY_ORDER.replace('chunk_type', 'c.chunk_type')}, "
                "c.id LIMIT %s",
                (subject.city, cap - len(rows)),
            ).fetchall()
    else:
        rows = []
        for pid in subject.poi_ids:
            rows += _rows(db, "poi_id = %s", (pid,), PER_DAY_STOP)
        rows = rows[:cap]
    keys = ("chunk_id", "poi_id", "city", "title", "body", "is_legend", "source_name", "source_url")
    seen: set[int] = set()
    facts = []
    for r in rows:
        if r[0] in seen:
            continue
        seen.add(r[0])
        d = dict(zip(keys, r, strict=True))
        d.pop("poi_id")
        facts.append(Fact(n=len(facts) + 1, **d))
    return facts


def fitting_length(requested: int, n_facts: int) -> int:
    """Rule 9: if the sources are thin, the story is shorter."""
    for length in (10, 5, 2):
        if length <= requested and n_facts >= NEED[length]:
            return length
    return 0
