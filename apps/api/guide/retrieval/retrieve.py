"""Hybrid retrieval over doc_chunk.

Two retrievers run independently and their rankings are fused with Reciprocal
Rank Fusion. Dense retrieval is pgvector cosine over the HNSW index and catches
paraphrase and other languages. Lexical retrieval is Postgres full text over
body_tsv and catches names, dates and spellings the embedding smooths away.

Both over-fetch twenty and the fused list is trimmed to k. Fetching k from each
would throw away exactly the rows that RRF is there to rescue.

Nothing here writes to the database. `db` is any psycopg connection.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .embed import embed_query

RRF_K = 60  # the standard RRF damping constant
OVERFETCH = 20  # rows pulled from each retriever before fusing
DEFAULT_K = 8

#: Below this cosine similarity the corpus has nothing to say. Calibrated
#: against the e5 model on the seeded corpus: real questions land at 0.82 and
#: above, nonsense at 0.80 and below.
MIN_SIMILARITY = 0.81

POI_BOOST = 0.15  # a chunk about the stop you are standing at
ACCESS_BOOST = 0.05  # a chunk that warns about steps, when the party needs it
ACCESS_WORDS = ("step", "steps", "climb", "accessib", "wheelchair", "ramp")

SELECT = """
    id, poi_id, city, title, body, chunk_type, is_legend,
    source_name, source_url
"""


class Filters(BaseModel):
    """Optional narrowing. exclude_ids keeps a Katha from repeating itself."""

    city: str | None = None
    poi_id: int | None = None
    chunk_type: str | None = None
    exclude_ids: list[int] = Field(default_factory=list)
    city_level_only: bool = False  # poi_id IS NULL: paragraphs about the city itself
    theme: str | None = None  # a city-layer theme


class TripContext(BaseModel):
    """What the planner knows about where the traveller is right now."""

    current_poi: int | None = None
    current_day: int | None = None
    has_elderly: bool = False


class Hit(BaseModel):
    id: int
    poi_id: int | None
    city: str | None
    title: str | None
    body: str
    chunk_type: str
    is_legend: bool
    source_name: str | None
    source_url: str | None
    score: float
    retrievers: list[str]
    dense_rank: int | None = None
    lexical_rank: int | None = None
    similarity: float | None = None


def _where(filters: Filters, extra: str = "") -> tuple[str, dict[str, Any]]:
    """Shared WHERE fragment so both retrievers filter identically."""
    # Retired rows are paragraphs no source file carries any more. They stay in
    # the table and never reach a Katha.
    clauses = ["NOT retired"] + ([extra] if extra else [])
    params: dict[str, Any] = {}
    if filters.city:
        clauses.append("city = %(city)s")
        params["city"] = filters.city
    if filters.poi_id is not None:
        clauses.append("poi_id = %(poi_id)s")
        params["poi_id"] = filters.poi_id
    if filters.chunk_type:
        clauses.append("chunk_type = %(chunk_type)s")
        params["chunk_type"] = filters.chunk_type
    if filters.city_level_only:
        clauses.append("poi_id IS NULL")
    if filters.theme:
        clauses.append("theme = %(theme)s")
        params["theme"] = filters.theme
    if filters.exclude_ids:
        clauses.append("id <> ALL(%(exclude_ids)s)")
        params["exclude_ids"] = list(filters.exclude_ids)
    return " AND ".join(clauses), params


def dense(db: Any, query: str, filters: Filters, limit: int = OVERFETCH) -> list[dict]:
    """Cosine nearest neighbours over the HNSW index, closest first."""
    where, params = _where(filters, "embedding IS NOT NULL")
    params["vec"] = "[" + ",".join(f"{x:.7f}" for x in embed_query(query)) + "]"
    params["limit"] = limit
    rows = db.execute(
        f"SELECT {SELECT}, 1 - (embedding <=> %(vec)s::vector) AS similarity "
        f"FROM doc_chunk WHERE {where} "
        f"ORDER BY embedding <=> %(vec)s::vector LIMIT %(limit)s",
        params,
    ).fetchall()
    return [_row(r, similarity=float(r[9])) for r in rows]


#: websearch_to_tsquery joins every term with AND, which is right for a search
#: box and wrong for a question. So the strict query runs first, and if it finds
#: nothing the same lexemes are re-run joined with OR, leaving ts_rank to order.
LEXICAL_SQL = """
WITH tq AS (SELECT {query} AS q)
SELECT {select} FROM doc_chunk, tq
WHERE {where} ORDER BY ts_rank(body_tsv, tq.q) DESC, id LIMIT %(limit)s
"""
STRICT_Q = "websearch_to_tsquery('english', %(q)s)"
LOOSE_Q = "replace(websearch_to_tsquery('english', %(q)s)::text, '&', '|')::tsquery"


def lexical(db: Any, query: str, filters: Filters, limit: int = OVERFETCH) -> list[dict]:
    """Postgres full text over body_tsv, best match first."""
    where, params = _where(filters, "body_tsv @@ tq.q")
    params["q"] = query
    params["limit"] = limit
    for parsed in (STRICT_Q, LOOSE_Q):
        rows = db.execute(
            LEXICAL_SQL.format(select=SELECT, query=parsed, where=where), params
        ).fetchall()
        if rows:
            strict = parsed is STRICT_Q
            return [_row(r) | {"strict": strict} for r in rows]
    return []


def _row(r: Any, similarity: float | None = None) -> dict:
    keys = ("id", "poi_id", "city", "title", "body", "chunk_type", "is_legend",
            "source_name", "source_url")
    return dict(zip(keys, r, strict=False)) | {"similarity": similarity}


def fuse(
    ranked: dict[str, list[dict]], rrf_k: int = RRF_K
) -> tuple[dict[int, float], dict[int, dict[str, int]]]:
    """Reciprocal Rank Fusion: each retriever adds 1/(k + rank) per row it found."""
    scores: dict[int, float] = {}
    ranks: dict[int, dict[str, int]] = {}
    for name, rows in ranked.items():
        for position, row in enumerate(rows, start=1):
            scores[row["id"]] = scores.get(row["id"], 0.0) + 1.0 / (rrf_k + position)
            ranks.setdefault(row["id"], {})[name] = position
    return scores, ranks


def rank(
    found: dict[str, list[dict]],
) -> tuple[dict[int, float], dict[int, dict[str, int]]]:
    """Fuse the retrievers that actually matched.

    The loose lexical fallback fires precisely when the strict query found
    nothing, and its rank one would carry the same weight as a confident dense
    rank one. So the fallback stays a standalone result and keeps out of the vote.
    """
    voting = {
        name: rows
        for name, rows in found.items()
        if rows and (name != "lexical" or rows[0].get("strict", True))
    }
    return fuse(voting or found)


def _expand(db: Any, query: str, context: TripContext) -> str:
    """Append the current stop and its city, so the query knows where it stands."""
    row = db.execute(
        "SELECT name, city FROM poi WHERE id = %s", (context.current_poi,)
    ).fetchone()
    return f"{query} {row[0]} {row[1]}" if row else query


def search(
    query: str,
    db: Any,
    *,
    filters: Filters | None = None,
    k: int = DEFAULT_K,
    trip_context: TripContext | None = None,
    min_similarity: float = MIN_SIMILARITY,
) -> list[Hit]:
    """Top k chunks for a query, or an empty list when the corpus has no answer.

    An empty list is a real answer: the caller says it does not know rather than
    narrate the closest thing it could find.
    """
    filters = filters or Filters()
    context = trip_context or TripContext()
    text = _expand(db, query, context) if context.current_poi is not None else query

    found = {"dense": dense(db, text, filters), "lexical": lexical(db, text, filters)}
    # Dense last, so a row both retrievers returned keeps the cosine it carries.
    by_id = {row["id"]: row for row in found["lexical"]}
    by_id.update({row["id"]: row for row in found["dense"]})
    if not by_id:
        return []

    # A loose lexical match is one common word in common, not evidence the corpus
    # can answer. Only a strict match counts as a second opinion.
    best = max((r["similarity"] or 0.0) for r in found["dense"]) if found["dense"] else 0.0
    if best < min_similarity and not any(r["strict"] for r in found["lexical"]):
        return []

    scores, ranks = rank(found)
    for chunk_id in scores:  # only rows that made it into the vote
        row = by_id[chunk_id]
        if context.current_poi is not None and row["poi_id"] == context.current_poi:
            scores[chunk_id] += POI_BOOST
        if context.has_elderly and any(w in row["body"].lower() for w in ACCESS_WORDS):
            scores[chunk_id] += ACCESS_BOOST

    order = sorted(scores, key=lambda i: (-scores[i], i))[:k]
    return [
        Hit(
            **{f: v for f, v in by_id[i].items() if f != "strict"},
            score=round(scores[i], 6),
            retrievers=sorted(ranks.get(i, {})),
            dense_rank=ranks.get(i, {}).get("dense"),
            lexical_rank=ranks.get(i, {}).get("lexical"),
        )
        for i in order
    ]
