"""Time /guide/ask on the eval set (card #40): retrieval and model, p50 and p95.

    cd apps/api && DATABASE_URL=... TY_FAKE_LLM=0 uv run python -m guide.scripts.bench_ask [N]

Runs the first N non-emergency eval questions (all when N is left out) through
ask() with the live model, one at a time and paced. Emergency questions are
skipped: they make no model call. The embedder is warmed before timing starts,
as main.py's startup warm-up does on Cloud Run.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

PAUSE_S = 2.0
EVAL = Path(__file__).resolve().parents[2] / "tests" / "guide" / "eval_ask.jsonl"


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p * (len(ordered) - 1)))]


async def main(n: int | None) -> None:
    import psycopg

    import guide
    ask_mod = importlib.import_module("guide.ask")  # the package re-exports a function named ask
    from guide.retrieval import retrieve
    from ty_contracts import GuideQuestion

    guide.warm_up()
    db = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    cases = [json.loads(line) for line in EVAL.read_text(encoding="utf-8").splitlines()]
    cases = [c for c in cases if c["expect"] not in ("emergency", "nearby")][:n]
    model, rows = ask_mod.answerer(), []
    real_search = retrieve.search

    def timed_search(*a, **k):
        start = time.monotonic()
        try:
            return real_search(*a, **k)
        finally:
            timings["retrieval"] += time.monotonic() - start

    for case in cases:
        await asyncio.sleep(PAUSE_S)
        timings = {"retrieval": 0.0}
        fields = {k: case[k] for k in ("question", "city", "place_name") if k in case}
        start = time.monotonic()
        answer = await ask_mod.ask(GuideQuestion(**fields), db, model, retrieve=timed_search)
        total = time.monotonic() - start
        rows.append((total, timings["retrieval"], bool(answer.citations), case["question"]))
        print(f"{total:5.2f}s  retrieval {timings['retrieval']:.2f}s  "
              f"{'cited' if answer.citations else 'refused'}  {case['question']}")  # fmt: skip
    totals = [r[0] for r in rows]
    print(f"\n{len(rows)} questions: p50 {statistics.median(totals):.2f}s  p95 {pct(totals, 0.95):.2f}s  "
          f"max {max(totals):.2f}s; retrieval p95 {pct([r[1] for r in rows], 0.95):.2f}s; "
          f"{sum(r[2] for r in rows)} cited")  # fmt: skip


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else None))
