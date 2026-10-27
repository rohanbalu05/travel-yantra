"""Build the Katha taste-gate pack (design/katha-style.md, "The taste gate").

Three subjects x three lengths. Each pair is the pipeline's Katha and a
plain-prompt version from the same model, written to data/katha/taste-gate/:

  blind/pair-NN/A.md, B.md   what raters read (order shuffled per pair)
  ratings.csv                one row per version to fill in, 1-5 per rubric line
  key/<subject>-<len>min/    katha.json, plain.md, notes.json (outline, critiques)
  key/key.json               which of A and B is the Katha; open after rating
  calls.log                  every live model call: time, step, result

Live calls, paced; re-running skips pairs already written. Run from apps/api:
  DATABASE_URL=... TY_FAKE_LLM=0 uv run python -m guide.scripts.katha_taste_gate
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import random
import time
from datetime import UTC, datetime
from pathlib import Path

from guide.katha.facts import gather, resolve
from guide.katha.pipeline import KathaFailed, plain_prompt, write
from guide.retrieval.seed import DATA, apply_migrations

OUT = DATA / "katha" / "taste-gate"
SUBJECTS = [("place", "Vittala Temple"), ("city", "Mysuru"), ("place", "Devaraja Market")]
LENGTHS = (2, 5, 10)
PAUSE_S = 4.0  # between live calls: the trial's Flash quota 429s on bursts
RUBRIC = ["hook", "theme", "specifics", "peak", "ending", "honesty"]
SEED = 24  # card #24; fixes the A/B shuffle so a re-run does not reshuffle


class LoggedModel:
    """core.llm's model, one call at a time, each logged to calls.log."""

    def __init__(self, model, log_path: Path):
        self.model, self.log_path, self.calls = model, log_path, 0

    async def _call(self, kind: str, step: str, fn):
        await asyncio.sleep(PAUSE_S)
        self.calls += 1
        start = time.monotonic()
        try:
            result = await fn()
            outcome = "ok"
            return result
        except Exception as e:
            outcome = f"error {type(e).__name__}: {str(e)[:160]}"
            raise
        finally:
            line = (f"{datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}\t{kind}\t{step}\t"
                    f"{time.monotonic() - start:.1f}s\t{outcome}\n")  # fmt: skip
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(line)

    async def json(self, prompt, schema, tier="lite", **kw):
        return await self._call("json", schema.__name__, lambda: self.model.json(prompt, schema, tier, **kw))

    async def text(self, prompt, tier="flash", **kw):
        step = "critique" if prompt.startswith("Here is a draft") else (
            "plain" if prompt.startswith("Write a ") and "\n" not in prompt else "draft")  # fmt: skip
        return await self._call("text", step, lambda: self.model.text(prompt, tier, **kw))


def slug(kind: str, name: str, length: int) -> str:
    return f"{name.lower().replace(' ', '-')}-{length}min"


def render(title: str, body: str, sources: list[str] = ()) -> str:
    out = f"# {title}\n\n{body.strip()}\n"
    if sources:
        out += "\n## Sources\n\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(sources, 1)) + "\n"
    return out


def katha_body(story) -> str:
    return "\n\n".join(f"*{s.label.title()}.* {s.text}" for s in story.segments)


async def main() -> None:
    import psycopg

    from core.llm import get_model

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "key").mkdir(exist_ok=True)
    model = LoggedModel(get_model(), OUT / "calls.log")
    db = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    apply_migrations(db)
    rng = random.Random(SEED)
    for kind, name in SUBJECTS:
        subject = resolve(db, kind, name)
        for length in LENGTHS:
            folder = OUT / "key" / slug(kind, name, length)
            if (folder / "katha.json").exists() and (folder / "plain.md").exists():
                continue
            folder.mkdir(exist_ok=True)
            facts = gather(db, subject, length)
            try:
                story, notes = await write(model, subject, length, facts)
            except KathaFailed as e:
                (folder / "failed.json").write_text(json.dumps(e.problems, indent=1), encoding="utf-8")
                print(f"FAILED {folder.name}: {e}")
                continue
            plain = await model.text(plain_prompt(subject, length), tier="flash", thinking="low",
                                     max_output_tokens=3500, temperature=0.7, timeout_s=60)  # fmt: skip
            (folder / "katha.json").write_text(story.model_dump_json(indent=1), encoding="utf-8")
            (folder / "notes.json").write_text(
                json.dumps({**notes, "facts": [f.model_dump() for f in facts]}, indent=1,
                           ensure_ascii=False), encoding="utf-8")  # fmt: skip
            (folder / "plain.md").write_text(plain.strip() + "\n", encoding="utf-8")
            print(f"wrote {folder.name} after {model.calls} calls")
    write_blind(rng)
    print(f"done: {model.calls} live model calls this run; see calls.log")


def write_blind(rng: random.Random) -> None:
    """Pair folders with shuffled A/B, the key, and the rating sheet."""
    from ty_contracts import KathaStory

    key, rows = {}, []
    done = sorted(p for p in (OUT / "key").iterdir() if (p / "katha.json").exists())
    order = list(range(len(done)))
    rng.shuffle(order)  # pairs are not in subject order either
    for n, i in enumerate(order, start=1):
        folder = done[i]
        pair = f"pair-{n:02d}"
        story = KathaStory.model_validate_json((folder / "katha.json").read_text(encoding="utf-8"))
        title = f"{story.subject}, {folder.name.rsplit('-', 1)[1].replace('min', ' minutes')}"
        versions = {
            "katha": render(title, katha_body(story), story.sources),
            "plain": render(title, (folder / "plain.md").read_text(encoding="utf-8")),
        }
        a_is_katha = rng.random() < 0.5
        blind = OUT / "blind" / pair
        blind.mkdir(parents=True, exist_ok=True)
        (blind / "A.md").write_text(versions["katha" if a_is_katha else "plain"], encoding="utf-8")
        (blind / "B.md").write_text(versions["plain" if a_is_katha else "katha"], encoding="utf-8")
        key[pair] = {"subject": folder.name, "katha": "A" if a_is_katha else "B"}
        rows += [[pair, v, *[""] * len(RUBRIC), ""] for v in ("A", "B")]
    (OUT / "key" / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    with (OUT / "ratings.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pair", "version", *RUBRIC, "preferred (A or B, on the A row)"])
        w.writerows(rows)


if __name__ == "__main__":
    asyncio.run(main())
