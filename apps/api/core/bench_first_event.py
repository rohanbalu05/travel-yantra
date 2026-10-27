"""Time to first streamed event (and to done) for POST /plan.

In process (times run_plan's first yield; no HTTP):  cd apps/api && TY_FAKE_LLM=1 uv run python -m core.bench_first_event
Over HTTP (local uvicorn or Cloud Run):               uv run python -m core.bench_first_event --url http://localhost:8080

Bodies: the Goa and Mysuru sample forms, plus one free-text request (--text to change it).
Prints p50 and p95 in seconds. Each run is one /plan request, so a live URL makes 3 model calls a run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx

SAMPLES = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "samples"
TEXT = "Bengaluru se Mysuru, 31 Oct se 1 Nov, hum do log, budget 15000"


def bodies(text: str) -> dict[str, dict]:
    out = {n: json.loads((SAMPLES / f"{n}.json").read_text(encoding="utf-8"))["request"]
           for n in ("goa_family", "mysuru_weekend")}
    out["free_text"] = {"text": text, "lang": "en"}
    return out


async def one(client: httpx.AsyncClient, body: dict) -> tuple[float, float, str]:
    """Seconds to the first `data:` frame and to the end of the stream, and the last stage seen."""
    t0 = time.perf_counter()
    first = None
    last = ""
    async with client.stream("POST", "/plan", json=body, timeout=120) as r:
        r.raise_for_status()
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                first = first or time.perf_counter() - t0
                last = json.loads(line[6:])["stage"]
    return first or float("nan"), time.perf_counter() - t0, last


async def one_in_process(body: dict) -> tuple[float, float, str]:
    from ty_contracts import PlanText, TripRequest

    from .pipeline import run_plan

    t0 = time.perf_counter()
    first = None
    last = ""
    parsed = PlanText.model_validate(body) if "text" in body else TripRequest.model_validate(body)
    async for event in run_plan(parsed):
        first = first or time.perf_counter() - t0
        last = event.stage.value
    return first or float("nan"), time.perf_counter() - t0, last


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p * (len(xs) - 1)))]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="deployed API base URL; omit to run in process")
    ap.add_argument("--runs", type=int, default=5, help="requests per body")
    ap.add_argument("--text", default=TEXT)
    args = ap.parse_args()
    async with httpx.AsyncClient(base_url=args.url or "http://unused") as client:
        print(f"target={args.url or 'in-process'} runs={args.runs} per body")
        for name, body in bodies(args.text).items():
            run = (lambda: one(client, body)) if args.url else (lambda: one_in_process(body))
            results = [await run() for _ in range(args.runs)]
            firsts, totals = [r[0] for r in results], [r[1] for r in results]
            print(f"{name:<15} first p50={statistics.median(firsts):.3f}s p95={pct(firsts, 0.95):.3f}s "
                  f"done p50={statistics.median(totals):.3f}s p95={pct(totals, 0.95):.3f}s last={results[-1][2]}")


if __name__ == "__main__":
    asyncio.run(main())
