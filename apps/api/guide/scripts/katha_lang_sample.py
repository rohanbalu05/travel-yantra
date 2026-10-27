"""One place's Katha in English and in another language from the same outline (rule 12),
for a native speaker to check. Needs no database: the facts come from the seed files
in the order gather() uses.

    cd apps/api && TY_FAKE_LLM=0 uv run python -m guide.scripts.katha_lang_sample \\
        ["Mysore Palace"] [2|5|10] [hi]

Writes data/katha/lang-samples/<place>-<len>min-<lang>/: en.md, <lang>.md and notes.json
(the shared outline, both critiques, the model calls with their times).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time

from guide.katha import katha_model
from guide.katha.facts import CAP, Fact, Subject
from guide.katha.pipeline import plan, write
from guide.planner import _slug
from guide.retrieval.seed import DATA, chunk_rows, load_pois

OUT = DATA / "katha" / "lang-samples"
ORDER = {"hook": 0, "story": 1, "sensory": 2, "fact": 3}


def facts_for(place: str, length: int) -> tuple[Subject, list[Fact]]:
    poi = next(p for p in load_pois()["pois"] if p["name"] == place)
    rows = [r for r in chunk_rows()[0]
            if r.get("poi") == place and r["chunk_type"] != "practical" and r.get("source_url")]  # fmt: skip
    rows.sort(key=lambda r: (r.get("tier") or 2, ORDER.get(r["chunk_type"], 4)))
    facts = [
        Fact(n=i + 1, chunk_id=i + 1, city=r["city"], title=r.get("title"), body=r["body"],
             is_legend=bool(r.get("is_legend")), source_name=r.get("source_name"),
             source_url=r.get("source_url"))
        for i, r in enumerate(rows[: CAP[length]])
    ]  # fmt: skip
    return Subject(kind="place", name=place, city=poi["city"], poi_ids=[0]), facts


def story_md(story) -> str:
    body = "\n\n".join(f"*{s.label}*  \n{s.text}" for s in story.segments)
    sources = "\n".join(f"{i}. {s}" for i, s in enumerate(story.sources, start=1))
    return f"# {story.subject} · {story.length_min} min · {story.lang}\n\n{body}\n\n## Sources\n\n{sources}\n"


async def main(place: str, length: int, lang: str) -> None:
    calls: list[str] = []

    class Collect(logging.Handler):
        def emit(self, record):
            calls.append(record.getMessage())

    logging.getLogger("guide.katha").addHandler(Collect())
    logging.getLogger("guide.katha").setLevel(logging.INFO)
    model = katha_model()
    subject, facts = facts_for(place, length)
    start = time.monotonic()
    outline = await plan(model, subject, length, facts)
    en, en_notes = await write(model, subject, length, facts, "en", outline=outline)
    other, other_notes = await write(model, subject, length, facts, lang, outline=outline)
    folder = OUT / f"{_slug(place)}-{length}min-{lang}"  # one pair, one outline, per folder
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "en.md").write_text(story_md(en), encoding="utf-8")
    (folder / f"{lang}.md").write_text(story_md(other), encoding="utf-8")
    notes = {"outline": outline.model_dump(), "critiques": {"en": en_notes["critiques"],
             lang: other_notes["critiques"]}, "trim": {"en": en_notes.get("trim"),
             lang: other_notes.get("trim")}, "calls": calls}  # fmt: skip
    (folder / "notes.json").write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{folder.relative_to(DATA.parent)}: {len(calls)} model calls, {time.monotonic() - start:.0f} s")


if __name__ == "__main__":
    args = sys.argv[1:]
    asyncio.run(main(args[0] if args else "Mysore Palace", int(args[1]) if len(args) > 1 else 2,
                     args[2] if len(args) > 2 else "hi"))  # fmt: skip
