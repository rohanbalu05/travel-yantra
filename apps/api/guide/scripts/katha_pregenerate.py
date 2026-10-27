"""Write Katha stories ahead of time into katha_cache, so the app never waits on a
first telling (several model calls: about a minute for 5 minutes, two for 10).

    cd apps/api && DATABASE_URL=... TY_FAKE_LLM=0 \\
        uv run python -m guide.scripts.katha_pregenerate [place:NAME | city:NAME ...]

With no arguments it writes the demo subjects at 2, 5 and 10 minutes. Cached
stories are skipped, so a re-run only spends calls on what is missing. Subjects
the corpus does not cover are reported and skipped, never invented.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

from guide.katha import KathaFailed, UnknownSubject, katha, katha_model
from guide.retrieval.seed import apply_migrations
from ty_contracts import KathaRequest

DEMO = ["city:Mysuru", "place:Mysore Palace", "place:Chamundeshwari Temple",
        "place:Vittala Temple", "city:Hampi", "place:Devaraja Market"]  # fmt: skip
LENGTHS = (2, 5, 10)


async def main(subjects: list[str]) -> int:
    import psycopg

    db = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    apply_migrations(db)
    model, failed = katha_model(), 0
    for spec in subjects:
        kind, _, name = spec.partition(":")
        for length in LENGTHS:
            start = time.monotonic()
            req = KathaRequest(subject_kind=kind, subject=name, length_min=length)
            try:
                story = await katha(req, db, model)
            except UnknownSubject:
                print(f"skip {spec}: not in the corpus")
                break
            except (KathaFailed, Exception) as e:  # one failure must not stop the batch
                failed += 1
                print(f"FAILED {spec} {length} min: {type(e).__name__}: {str(e)[:200]}")
                continue
            print(f"ok {spec} {length} min -> {story.length_min} min, "
                  f"{len(story.text.split())} words, {time.monotonic() - start:.0f} s")  # fmt: skip
    return 1 if failed else 0


def log_calls() -> None:
    """Every model call's step, time and tokens in the job's logs: guide.katha and core.llm
    log at INFO, which an unconfigured script drops. TY_LOG_LEVEL overrides."""
    level = os.environ.get("TY_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    for name in ("guide.katha", "core.llm", "guide.places"):
        logging.getLogger(name).setLevel(level)


if __name__ == "__main__":
    log_calls()
    sys.exit(asyncio.run(main(sys.argv[1:] or DEMO)))
