"""Katha: stories of a place, a city or a trip day (card #24, design/katha-style.md)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ty_contracts import KathaRequest, KathaStory, Lang

from .facts import FIELD_NOTES, OUR_NOTES, UnknownSubject, gather, resolve
from .pipeline import LANGS, KathaFailed, Outline, write

__all__ = ["LENGTHS_SERVED", "KathaFailed", "KathaRequest", "UnknownSubject", "katha", "katha_model"]

#: Bump when prompts or checks change, so cached stories are rewritten.
PIPELINE_VERSION = "8"
#: 10-minute stories are off until they pass (HQ P7): chapter-by-chapter retelling still
#: fails its checks too often to ship. TY4 hides the option; the pipeline keeps them.
LENGTHS_SERVED = {2, 5}


def katha_model() -> Any:
    from core.llm import fake_enabled, get_model

    if fake_enabled():
        from .fake import FakeKathaModel

        return FakeKathaModel()
    return get_model()


def story_lang(req: KathaRequest) -> Lang:
    """The language the story is written in: the request's when Katha has a voice for it
    (rule 12), else English, which the translate service carries to the rest."""
    return req.lang if req.lang in LANGS else Lang.en


def key_inputs(req: KathaRequest, subject_name: str, chunk_ids: list[int]) -> list:
    """What the cache key hashes; kept in katha_cache.notes so two keys can be compared.
    English keeps its key shape, so the cached English stories stay valid."""
    inputs = [PIPELINE_VERSION, req.subject_kind, subject_name, req.length_min, chunk_ids]
    return inputs if story_lang(req) == Lang.en else [*inputs, story_lang(req).value]


def cache_key(req: KathaRequest, subject_name: str, chunk_ids: list[int]) -> str:
    raw = json.dumps(key_inputs(req, subject_name, chunk_ids), sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def labelled(story: KathaStory) -> KathaStory:
    """Our own notes named one way, "Travel Yantra field notes", in stories cached before
    the label was settled (HQ P7)."""
    sources = [FIELD_NOTES if not s.strip() or s.strip().lower() in OUR_NOTES else s for s in story.sources]
    return story if sources == story.sources else story.model_copy(update={"sources": sources})


def _cached(db: Any, key: str) -> tuple[dict, dict] | None:
    row = db.execute("SELECT story, notes FROM katha_cache WHERE key = %s", (key,)).fetchone()
    return (row[0], row[1] or {}) if row else None


async def katha(req: KathaRequest, db: Any, model: Any) -> KathaStory:
    """A cached story, or a new one written, checked and cached.

    Another language is told from the English story's outline (rule 12): the cached
    one's, or a new English story is written (and cached) first."""
    subject = resolve(db, req.subject_kind, req.subject, req.places)
    if subject.kind != req.subject_kind:  # a place request that named a city: the city's story
        req = req.model_copy(update={"subject_kind": subject.kind, "subject": subject.name})
    facts = gather(db, subject, req.length_min)
    chunk_ids = [f.chunk_id for f in facts]
    key = cache_key(req, subject.name, chunk_ids)
    if hit := _cached(db, key):
        return labelled(KathaStory.model_validate(hit[0]))
    lang = story_lang(req)
    outline = None
    if lang != Lang.en:
        english = req.model_copy(update={"lang": Lang.en})
        await katha(english, db, model)  # cached, or written now
        notes = (_cached(db, cache_key(english, subject.name, chunk_ids)) or ({}, {}))[1]
        if notes.get("outline"):
            outline = Outline.model_validate(notes["outline"])
    story, notes = await write(model, subject, req.length_min, facts, lang=lang, outline=outline)
    db.execute(
        "INSERT INTO katha_cache (key, story, notes) VALUES (%s, %s::jsonb, %s::jsonb) "
        "ON CONFLICT (key) DO NOTHING",
        (key, story.model_dump_json(), json.dumps(notes | {"key_inputs": key_inputs(
            req, subject.name, chunk_ids)})),  # fmt: skip
    )
    return story
