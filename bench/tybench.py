"""TY-Bench: Travel Yantra's /plan against one plain Gemini prompt, on 30 fixed requests.

    cd apps/api
    uv run python ../../bench/tybench.py --dry-run          # the first 3 requests, both arms
    uv run python ../../bench/tybench.py --full             # all 30 (only after HQ's freeze)
    uv run python ../../bench/tybench.py --only b07 --arm ty

Arms:
  ty        POST {API}/plan on the live ty-api (SSE), the plan in the "done" event.
            Tokens: ty-api's own usage lines in Cloud Logging for the request's time
            window (requests run one at a time; other traffic in that window would
            count too, so the full run waits for the freeze).
  baseline  One Gemini call (TY_MODEL_FLASH, default gemini-3.5-flash) on Vertex AI:
            the same request, the Itinerary JSON schema, "plan this trip". No tools,
            no places data, no checker. Tokens from the response's usage metadata.

Both plans are scored the same way (score.py): TY1's checker (core.checker.check,
haversine road times, no live calls) for hours, travel time, constraints and
budget, plus the bench's own meal check and whether the plan covers the asked
dates. Results go to bench/results/<run>.jsonl and a summary table is printed.
Live model calls: never from tests. Every call here is a paid Vertex call on the
trial credit (about 300 Flash calls for a full run, both arms).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from score import score  # noqa: E402

DEFAULT_API = "https://ty-api-643396702106.asia-south1.run.app"
PROJECT = "project-cea09bbb-b5f7-4fc4-95b"
PAUSE_S = 5.0
PLAN_TIMEOUT_S = 240


def load_requests() -> list[dict]:
    lines = (HERE / "requests.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines if x.strip()]


def prices() -> dict:
    return json.loads((HERE / "prices.json").read_text(encoding="utf-8"))


def inr(model: str, prompt: int, output: int, table: dict) -> float | None:
    p = table["per_million_usd"].get(model) or {}
    if p.get("input") is None or p.get("output") is None:
        return None
    return round(
        (prompt * p["input"] + output * p["output"]) / 1e6 * table["usd_inr"], 3
    )


# ---- the ty arm ----


def run_ty(row: dict, api: str) -> dict:
    import httpx

    t0 = time.monotonic()
    start = datetime.now(timezone.utc)
    first = None
    done = None
    last = None
    try:
        with httpx.stream(
            "POST",
            f"{api}/plan",
            json=row["request"],
            timeout=PLAN_TIMEOUT_S,
            headers={"Accept": "text/event-stream", "X-Client-Id": "tybench"},
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                ev = json.loads(line[5:].strip())
                first = first if first is not None else time.monotonic() - t0
                last = ev
                if ev.get("stage") in ("done", "needs_input", "error"):
                    done = ev
                    break
    except Exception as e:  # noqa: BLE001 - a failed plan is a result
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "seconds": round(time.monotonic() - t0, 2),
        }
    seconds = round(time.monotonic() - t0, 2)
    end = datetime.now(timezone.utc)
    out = {
        "seconds": seconds,
        "first_event_s": round(first, 2) if first is not None else None,
        "stage": (done or last or {}).get("stage"),
        "window": [start.isoformat(), end.isoformat()],
    }
    if done and done.get("stage") == "done" and done.get("partial"):
        out.update(ok=True, plan=done["partial"])
    else:
        out.update(ok=False, error=(done or last or {}).get("message", "no done event"))
    return out


def ty_usage(window: list[str]) -> dict | None:
    """Sum ty-api's model usage lines (core.llm.log_usage) logged inside the window."""
    flt = (
        f'resource.type="cloud_run_revision" resource.labels.service_name="ty-api" '
        f'textPayload:"model=" timestamp>="{window[0]}" timestamp<="{window[1]}"'
    )
    try:
        raw = subprocess.run(
            [
                "gcloud",
                "logging",
                "read",
                flt,
                "--project",
                PROJECT,
                "--format",
                "json",
                "--limit",
                "500",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            shell=os.name == "nt",
        )
        entries = json.loads(raw.stdout or "[]")
    except Exception:  # noqa: BLE001
        return None
    n = {"calls": 0, "prompt": 0, "output": 0, "thoughts": 0, "models": {}}
    for e in entries:
        words = dict(
            w.split("=", 1) for w in (e.get("textPayload") or "").split() if "=" in w
        )
        if "total" not in words:
            continue
        n["calls"] += 1
        n["prompt"] += int(words.get("prompt", 0))
        n["output"] += int(words.get("output", 0))
        n["thoughts"] += int(words.get("thoughts", 0))
        n["models"][words.get("model", "?")] = (
            n["models"].get(words.get("model", "?"), 0) + 1
        )
    return n


# ---- the baseline arm ----

BASELINE_PROMPT = """You are a travel planner for India. Plan this trip.

Trip request (JSON):
{request}

In the traveller's words: {text}

Return only JSON that matches this JSON schema (an Itinerary). Copy the request
into "request" unchanged. Give one DayPlan per date from start_date to end_date.
For each stop give a real place with its latitude, longitude, category, opening
hours and typical visit minutes, and give each day a schedule (arrive, start,
leave as local ISO times) and road legs between stops. Fill budget with your
estimate in rupees.

Schema:
{schema}
"""


def run_baseline(row: dict, model: str) -> dict:
    from google import genai
    from google.genai import types

    from ty_contracts import Itinerary

    client = genai.Client()
    prompt = BASELINE_PROMPT.format(
        request=json.dumps(row["request"], ensure_ascii=False),
        text=row["text"],
        schema=json.dumps(Itinerary.model_json_schema(by_alias=True)),
    )
    t0 = time.monotonic()
    try:
        r = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
                max_output_tokens=32768,
            ),
        )
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "seconds": round(time.monotonic() - t0, 2),
        }
    seconds = round(time.monotonic() - t0, 2)
    u = r.usage_metadata
    usage = {
        "calls": 1,
        "prompt": u.prompt_token_count or 0,
        "output": u.candidates_token_count or 0,
        "thoughts": u.thoughts_token_count or 0,
        "models": {model: 1},
    }
    try:
        plan = json.loads(r.text or "")
    except json.JSONDecodeError as e:
        return {
            "ok": False,
            "error": f"not JSON: {e}",
            "seconds": seconds,
            "usage": usage,
        }
    return {"ok": True, "plan": plan, "seconds": seconds, "usage": usage}


# ---- the run ----


def cost(usage: dict | None, table: dict) -> float | None:
    if not usage or not usage["calls"]:
        return None
    total, known = 0.0, True
    # Split tokens across models by call count (log lines carry per-call counts, but the
    # sum is what the run needs; a run on one model is exact).
    calls = usage["calls"]
    for model, k in usage["models"].items():
        share = k / calls
        c = inr(
            model,
            round(usage["prompt"] * share),
            round((usage["output"] + usage["thoughts"]) * share),
            table,
        )
        if c is None:
            known = False
        else:
            total += c
    return round(total, 3) if known else None


def pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, round(p * (len(s) - 1)))]


def summarise(results: list[dict]) -> None:
    dims = ["valid", "dates", "hours", "travel_time", "meals", "budget", "constraints"]
    print(
        f"\n{'arm':9} {'n':>3} "
        + " ".join(f"{d:>11}" for d in dims)
        + f" {'p50 s':>7} {'p95 s':>7} {'tokens':>8} {'₹/plan':>8}"
    )
    for arm in ("ty", "baseline"):
        rs = [r for r in results if r["arm"] == arm]
        if not rs:
            continue
        cells = []
        for d in dims:
            ok = sum(1 for r in rs if r["score"][d])
            cells.append(f"{ok:>4}/{len(rs):<6}")
        secs = [r["seconds"] for r in rs if r.get("seconds") is not None]
        toks = [
            r["usage"]["prompt"] + r["usage"]["output"] + r["usage"]["thoughts"]
            for r in rs
            if r.get("usage")
        ]
        costs = [r["inr"] for r in rs if r.get("inr") is not None]
        f = lambda v, fmt: (fmt % v) if v is not None else "-"  # noqa: E731
        print(
            f"{arm:9} {len(rs):>3} "
            + " ".join(f"{c:>11}" for c in cells)
            + f" {f(pct(secs, 0.5), '%7.1f')} {f(pct(secs, 0.95), '%7.1f')}"
            + f" {f(statistics.mean(toks) if toks else None, '%8.0f')} {f(statistics.mean(costs) if costs else None, '%8.2f')}"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="the first 3 requests")
    g.add_argument("--full", action="store_true", help="all 30 (after HQ's freeze)")
    g.add_argument("--only", help="comma-separated ids, e.g. b01,b07")
    ap.add_argument("--arm", choices=["ty", "baseline", "both"], default="both")
    ap.add_argument("--api", default=os.getenv("TY_BENCH_API", DEFAULT_API))
    ap.add_argument(
        "--no-logs",
        action="store_true",
        help="skip reading ty-api's token usage from Cloud Logging",
    )
    a = ap.parse_args()

    rows = load_requests()
    if a.dry_run:
        rows = rows[:3]
    elif a.only:
        want = set(a.only.split(","))
        rows = [r for r in rows if r["id"] in want]
    model = os.getenv("TY_MODEL_FLASH", "gemini-3.5-flash")
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    table = prices()
    run = datetime.now().strftime("%Y%m%d-%H%M%S") + ("-dry" if a.dry_run else "")
    out = HERE / "results" / f"{run}.jsonl"
    out.parent.mkdir(exist_ok=True)
    arms = ["ty", "baseline"] if a.arm == "both" else [a.arm]
    results = []
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            for arm in arms:
                r = run_ty(row, a.api) if arm == "ty" else run_baseline(row, model)
                if arm == "ty" and r.get("window") and not a.no_logs:
                    time.sleep(10)  # let Cloud Logging catch up
                    r["usage"] = ty_usage(r["window"])
                r["inr"] = cost(r.get("usage"), table)
                r["score"] = score(
                    r.get("plan") if r.get("ok") else None, row["request"]
                )
                rec = {
                    "id": row["id"],
                    "region": row["region"],
                    "persona": row["persona"],
                    "arm": arm,
                    **{k: v for k, v in r.items() if k != "plan"},
                }
                f.write(
                    json.dumps({**rec, "plan": r.get("plan")}, ensure_ascii=False)
                    + "\n"
                )
                results.append(rec)
                s = r["score"]
                print(
                    f"{row['id']} {arm:8} ok={r.get('ok')} {r.get('seconds')}s "
                    f"violations={s['violations']} meals={s['meals']} dates={s['dates']} ₹={r.get('inr')}"
                    + (f" error={r.get('error')[:120]}" if r.get("error") else ""),
                    flush=True,
                )
                time.sleep(PAUSE_S)
    summarise(results)
    print(f"\nresults: {out.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
