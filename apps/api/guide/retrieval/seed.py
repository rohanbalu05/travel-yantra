"""Seed data for the guide: row builders (pure) and the loader (needs Postgres).

Sources, all under data/:
  pois.json            POIs, relations between them, intercity legs, advisories
  chunks_curated.json  hand-written paragraphs, authoritative
  chunks.json          generated paragraphs that fill the gaps around them
  chunks_city.json     city-layer paragraphs plus retags (theme/tier) of existing rows

Everything upserts on a natural key, so re-running is safe. Nothing is deleted:
a chunk no source file carries any more is marked retired.
"""

from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path
from typing import Any

from .embed import BATCH, CITY_KN, chunk_text, embed_passages

DATA = Path(__file__).resolve().parents[4] / "data"
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
CURATED_DATE = "2026-08-27"
CITY_DATE = "2026-08-28"

#: Locality in the curated file -> hub city in the poi table.
HUB = {"Srirangapatna": "Mysuru", "Belur": "Chikmagalur", "Halebidu": "Chikmagalur"}

#: Short place name in the curated file -> full name in the poi table.
POI_ALIAS = {
    "Chamundi Hill": "Chamundeshwari Temple",
    "Daria Daulat Bagh": "Daria Daulat Bagh (Tipu Sultan's Summer Palace), Srirangapatna",
    "Vittala Temple": "Vittala Temple and Stone Chariot",
    "Chennakeshava Temple": "Chennakeshava Temple, Belur",
    "Hoysaleswara Temple": "Hoysaleswara Temple, Halebidu",
    "Bull Temple": "Bull Temple (Dodda Basavana Gudi)",
    "Mullayanagiri": "Mullayanagiri Peak",
}

POI_COLS = [
    "name", "name_kn", "city", "district", "lat", "lng", "category", "tags",
    "typical_dwell_min", "entry_fee_inr", "opens", "closes", "closed_on",
    "best_time", "accessibility_notes", "elderly_friendly", "popularity",
    "source_url", "last_verified", "trust",
]  # fmt: skip
POI_DEFAULTS = {
    "tags": [], "closed_on": [], "entry_fee_inr": 0, "elderly_friendly": True,
    "trust": "draft",
}  # fmt: skip


def _load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def load_pois() -> dict:
    """The curated Karnataka corpus plus every built corridor (data/corridor/*_pois.json)."""
    data = _load("pois.json")
    for path in sorted((DATA / "corridor").glob("*_pois.json")):
        data["pois"] = data["pois"] + json.loads(path.read_text(encoding="utf-8"))["pois"]
    return data


def poi_row(p: dict) -> dict:
    row = {c: p.get(c, POI_DEFAULTS.get(c)) for c in POI_COLS}
    row["opens"] = time.fromisoformat(row["opens"]) if row["opens"] else None
    row["closes"] = time.fromisoformat(row["closes"]) if row["closes"] else None
    row["last_verified"] = (
        date.fromisoformat(row["last_verified"]) if row["last_verified"] else None
    )
    return row


def chunk_rows() -> tuple[list[dict], list[dict]]:
    """(every paragraph to upsert, theme/tier retags of existing paragraphs)."""
    rows = []
    for c in _load("chunks_curated.json")["chunks"]:
        name = c.get("poi_name")
        rows.append({
            **c,
            "poi": POI_ALIAS.get(name, name) if name else None,
            "city": HUB.get(c["city"], c["city"]),
            "last_verified": CURATED_DATE,
        })  # fmt: skip
    rows += [{"lang": "en", **c} for c in _load("chunks.json")["chunks"]]
    for path in sorted((DATA / "corridor").glob("*_chunks.json")):
        rows += json.loads(path.read_text(encoding="utf-8"))["chunks"]
    retags = []
    for c in _load("chunks_city.json")["chunks"]:
        if "body" in c:
            rows.append({"lang": "en", "last_verified": CITY_DATE, **c})
        else:
            retags.append(c)
    for r in rows:
        r.setdefault("lang", "en")
    return rows, retags


UPSERT_CHUNK = """
INSERT INTO doc_chunk
    (poi_id, city, title, body, chunk_type, is_legend, lang, source_name,
     source_url, last_verified, aliases, retired, theme, tier)
VALUES
    (%(poi_id)s, %(city)s, %(title)s, %(body)s, %(chunk_type)s, %(is_legend)s,
     %(lang)s, %(source_name)s, %(source_url)s, %(last_verified)s, %(aliases)s,
     false, %(theme)s, %(tier)s)
ON CONFLICT (city, title) DO UPDATE SET
    poi_id = excluded.poi_id, body = excluded.body,
    chunk_type = excluded.chunk_type, is_legend = excluded.is_legend,
    source_name = excluded.source_name, source_url = excluded.source_url,
    last_verified = excluded.last_verified, aliases = excluded.aliases,
    retired = false,
    theme = coalesce(excluded.theme, doc_chunk.theme),
    tier = coalesce(excluded.tier, doc_chunk.tier),
    embedding = CASE
        WHEN doc_chunk.body IS DISTINCT FROM excluded.body
          OR doc_chunk.aliases IS DISTINCT FROM excluded.aliases THEN NULL
        ELSE doc_chunk.embedding
    END
"""


def apply_migrations(conn: Any) -> None:
    for path in sorted(MIGRATIONS.glob("*.sql")):
        conn.execute(path.read_text(encoding="utf-8"))


def load_seed(conn: Any, *, reembed: bool = False) -> dict[str, int]:
    """Upsert POIs, relations and chunks, then embed rows that lack a vector."""
    data = load_pois()
    ids = {}
    for p in data["pois"]:
        cols = ", ".join(POI_COLS)
        marks = ", ".join(f"%({c})s" for c in POI_COLS)
        sets = ", ".join(f"{c} = excluded.{c}" for c in POI_COLS)
        ids[p["name"]] = conn.execute(
            f"INSERT INTO poi ({cols}) VALUES ({marks}) "
            f"ON CONFLICT (name, city) DO UPDATE SET {sets} RETURNING id",
            poi_row(p),
        ).fetchone()[0]
    for e in data["edges"]:
        conn.execute(
            "INSERT INTO poi_edge (from_poi, to_poi, relation, weight) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (ids[e["from"]], ids[e["to"]], e["relation"], e.get("weight", 1.0)),
        )
    for leg in data["intercity_legs"]:
        for a, b in ((leg["from"], leg["to"]), (leg["to"], leg["from"])):
            conn.execute(
                "INSERT INTO intercity_leg "
                "(from_city, to_city, mode, distance_km, duration_min, notes) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (a, b, leg["mode"], leg.get("distance_km"), leg["duration_min"],
                 leg.get("notes")),
            )  # fmt: skip
    for a in data["advisories"]:
        conn.execute(
            "INSERT INTO advisory (poi_id, city, severity, message, source, valid_until) "
            "VALUES (%s, %s, %s, %s, %s, current_date + %s) ON CONFLICT DO NOTHING",
            (ids.get(a.get("poi")), a.get("city"), a["severity"], a["message"],
             a["source"], a["valid_days"]),
        )  # fmt: skip

    pois = {
        (name, city): (pid, name_kn)
        for pid, name, city, name_kn in conn.execute(
            "SELECT id, name, city, name_kn FROM poi"
        )
    }
    rows, retags = chunk_rows()
    live = set()
    for r in rows:
        key = (r["city"], r["title"])
        if key in live:
            raise ValueError(f"duplicate (city, title): {key}")
        live.add(key)
        if r["poi"] and (r["poi"], r["city"]) not in pois:
            raise ValueError(f"chunk names unknown poi {r['poi']!r} in {r['city']}")
        pid, name_kn = pois.get((r["poi"], r["city"]), (None, None))
        conn.execute(
            UPSERT_CHUNK,
            {
                **{k: r.get(k) for k in (
                    "city", "title", "body", "chunk_type", "source_name",
                    "source_url", "lang", "theme", "tier")},
                "poi_id": pid,
                "is_legend": bool(r.get("is_legend")),
                "last_verified": date.fromisoformat(r["last_verified"]),
                # aliases feed body_tsv: what the chunk is about, not where
                "aliases": " | ".join(n for n in (r["poi"], name_kn) if n),
            },
        )  # fmt: skip
    for t in retags:
        cur = conn.execute(
            "UPDATE doc_chunk SET theme = %s, tier = %s "
            "WHERE city = %s AND title = %s AND NOT retired",
            (t["theme"], t["tier"], t["city"], t["title"]),
        )
        if cur.rowcount != 1:
            raise ValueError(f"retag found no live row: {t['city']!r} / {t['title']!r}")
    for city, title in conn.execute(
        "SELECT city, title FROM doc_chunk WHERE NOT retired"
    ).fetchall():
        if (city, title) not in live:
            conn.execute(
                "UPDATE doc_chunk SET retired = true WHERE city = %s AND title = %s",
                (city, title),
            )

    if reembed:
        conn.execute("UPDATE doc_chunk SET embedding = NULL WHERE NOT retired")
    todo = conn.execute(
        "SELECT id, title, body, aliases, city FROM doc_chunk "
        "WHERE embedding IS NULL AND NOT retired ORDER BY id"
    ).fetchall()
    for start in range(0, len(todo), BATCH):
        batch = todo[start : start + BATCH]
        vectors = embed_passages([
            chunk_text(title, body, [*(aliases.split(" | ") if aliases else []),
                                     city, CITY_KN.get(city, "")])
            for _, title, body, aliases, city in batch
        ])  # fmt: skip
        for vec, row in zip(vectors, batch, strict=True):
            conn.execute(
                "UPDATE doc_chunk SET embedding = %s::vector WHERE id = %s",
                ("[" + ",".join(f"{x:.7f}" for x in vec) + "]", row[0]),
            )
    return {
        t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        for t in ("poi", "poi_edge", "intercity_leg", "advisory")
    } | {
        "doc_chunk_live": conn.execute(
            "SELECT count(*) FROM doc_chunk WHERE NOT retired"
        ).fetchone()[0],
        "legends": conn.execute(
            "SELECT count(*) FROM doc_chunk WHERE NOT retired AND is_legend"
        ).fetchone()[0],
    }
