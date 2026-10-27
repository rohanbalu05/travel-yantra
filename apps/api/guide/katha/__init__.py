"""Katha: stories of a place, a city or a trip day (card #24, design/katha-style.md)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ty_contracts import KathaRequest, KathaStory, Lang

from .facts import UnknownSubject, gather, resolve
from .pipeline import KathaFailed, write

__all__ = ["KathaFailed", "KathaRequest", "UnknownSubject", "katha", "katha_model"]

#: Bump when prompts or checks change, so cached stories are rewritten.
PIPELINE_VERSION = "4"


def katha_model() -> Any:
    from core.llm import fake_enabled, get_model

    if fake_enabled():
        from .fake import FakeKathaModel

        return FakeKathaModel()
    return get_model()


def cache_key(req: KathaRequest, subject_name: str, chunk_ids: list[int]) -> str:
    raw = json.dumps([PIPELINE_VERSION, req.subject_kind, subject_name, req.length_min,
                      req.lang, chunk_ids], sort_keys=True)  # fmt: skip
    return hashlib.sha256(raw.encode()).hexdigest()


async def katha(req: KathaRequest, db: Any, model: Any) -> KathaStory:
    """A cached story, or a new one written, checked and cached."""
    subject = resolve(db, req.subject_kind, req.subject, req.places)
    facts = gather(db, subject, req.length_min)
    key = cache_key(req, subject.name, [f.chunk_id for f in facts])
    if row := db.execute("SELECT story FROM katha_cache WHERE key = %s", (key,)).fetchone():
        return KathaStory.model_validate(row[0])
    # The guide writes English for now; other languages come from the same outline later.
    story, notes = await write(model, subject, req.length_min, facts, lang=Lang.en)
    db.execute(
        "INSERT INTO katha_cache (key, story, notes) VALUES (%s, %s::jsonb, %s::jsonb) "
        "ON CONFLICT (key) DO NOTHING",
        (key, story.model_dump_json(), json.dumps(notes)),
    )
    return story
