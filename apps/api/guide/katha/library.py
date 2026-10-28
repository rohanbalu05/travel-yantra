"""GET /guide/katha/library (HQ P7): every place and city with a story ready to tell.

Read from katha_cache: stories of the current PIPELINE_VERSION, told at the length that
was asked for (a thin place's 5-minute request that came back as 2 minutes lists 2), at
the lengths the API serves. Day stories come from a plan, so they are not listed.
Remembered for a few minutes per instance: the cache only grows when a story is written.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ty_contracts import KathaStory

from . import voice

TTL_S = 300
_memo: dict[str, tuple[float, list[dict]]] = {}


def library(db: Any, *, attach=voice.attach) -> list[dict]:
    from . import LENGTHS_SERVED, PIPELINE_VERSION

    if (hit := _memo.get("all")) and hit[0] > time.monotonic():
        return hit[1]
    rows = db.execute(
        "SELECT c.story, p.city, p.popularity FROM katha_cache c "
        "LEFT JOIN poi p ON c.story->>'subject_kind' = 'place' AND p.name = c.story->>'subject' "
        "WHERE c.notes->'key_inputs'->>0 = %s AND c.story->>'subject_kind' IN ('place', 'city') "
        "AND (c.story->>'length_min')::int = (c.notes->'key_inputs'->>3)::int",
        (PIPELINE_VERSION,),
    ).fetchall()
    stories = [(KathaStory.model_validate(r[0]), r[1], r[2]) for r in rows]
    stories = [s for s in stories if s[0].length_min in LENGTHS_SERVED]
    with ThreadPoolExecutor(max_workers=8) as pool:  # one small public GET each, remembered
        audio = list(pool.map(lambda s: bool(attach(s[0])), stories))
    items: dict[tuple[str, str], dict] = {}
    for (story, city, popularity), has_audio in zip(stories, audio, strict=True):
        item = items.setdefault((story.subject_kind, story.subject), {
            "subject_kind": story.subject_kind, "subject": story.subject,
            "city": city if story.subject_kind == "place" else story.subject,
            "lengths": set(), "langs": set(), "has_audio": False, "_rank": popularity or 0,
        })  # fmt: skip
        item["lengths"].add(story.length_min)
        item["langs"].add(story.lang.value if hasattr(story.lang, "value") else story.lang)
        item["has_audio"] |= has_audio
    out = [
        {**{k: v for k, v in i.items() if k != "_rank"}, "lengths": sorted(i["lengths"]), "langs": sorted(i["langs"])}
        for i in sorted(items.values(), key=lambda i: (i["subject_kind"] != "city", -i["_rank"], i["subject"]))
    ]
    _memo["all"] = (time.monotonic() + TTL_S, out)
    return out
