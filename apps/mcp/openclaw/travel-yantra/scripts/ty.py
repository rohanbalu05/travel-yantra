"""Travel Yantra from the command line, for the OpenClaw skill (stdlib only).

    python3 ty.py plan "Bengaluru to Mysuru, 31 Oct to 1 Nov, 2 of us" [--lang hi]
    python3 ty.py revise PLAN_ID rain [--day 2026-11-01] [--place-id ID] [--city Mysuru] [--mode rail]
    python3 ty.py compare Bengaluru Mysuru [--on 2026-10-31] [--rank-by balanced]
    python3 ty.py katha "Mysore Palace" [--minutes 2|5|10] [--lang hi] [--kind place|city]
    python3 ty.py ask "nearest hospital" [--lang en] [--lat 15.49 --lng 73.82]
    python3 ty.py pnr 1234567890

Prints one JSON object. Env: TRAVEL_YANTRA_API (default: the public API),
TRAVEL_YANTRA_WEB (share links). Exit 1 with {"error": ...} when the API refuses.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://ty-api-643396702106.asia-south1.run.app"
WEB = "https://ty-web-643396702106.asia-south1.run.app"
LANGS = ["en", "hi", "kn", "ta", "te", "bn"]
PLAN_TIMEOUT = 180  # a first plan can take about a minute


class ApiError(Exception):
    pass


def base() -> str:
    return os.environ.get("TRAVEL_YANTRA_API", API).rstrip("/")


def share_url(token: str | None) -> str | None:
    web = os.environ.get("TRAVEL_YANTRA_WEB", WEB).rstrip("/")
    return f"{web}/t/{token}/" if token else None


def _detail(e: urllib.error.HTTPError) -> str:
    try:
        detail = json.loads(e.read()).get("detail")
    except ValueError:
        detail = None
    if isinstance(detail, list):
        detail = "; ".join(str(d.get("msg", d)) for d in detail if isinstance(d, dict))
    return f"HTTP {e.code}: {detail}" if detail else f"HTTP {e.code}"


def request(method: str, path: str, body: dict | None = None, timeout: float = 60, opener=None):
    """The API's response: parsed JSON, or the raw response for event streams."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base() + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        return (opener or urllib.request.urlopen)(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise ApiError(_detail(e)) from e
    except urllib.error.URLError as e:
        raise ApiError(f"cannot reach the API: {e.reason}") from e


def get_json(method: str, path: str, body: dict | None = None, opener=None) -> dict:
    with request(method, path, body, opener=opener) as r:
        return json.loads(r.read())


def stream_plan(path: str, body: dict, opener=None) -> dict:
    """Read /plan's server-sent PlanEvents to the end: the plan, or the planner's questions."""
    final = None
    with request("POST", path, body, timeout=PLAN_TIMEOUT, opener=opener) as r:
        for raw in r:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue  # blank separators and ": ping" keep-alives
            event = json.loads(line[5:])
            stage = event.get("stage")
            if stage == "error":
                raise ApiError(event.get("message") or "planning failed")
            if stage == "needs_input":
                return {"needs_input": event.get("questions", []), "draft": event.get("draft")}
            if event.get("partial") is not None:
                final = event["partial"]
            if stage == "done":
                if final is None:
                    break
                return {
                    "plan_id": event.get("plan_id"),
                    "share_url": share_url(event.get("share_token")),
                    "itinerary": final,
                }
    raise ApiError("the plan finished without an itinerary")


def run(args: argparse.Namespace, opener=None) -> dict:
    if args.cmd == "plan":
        return stream_plan("/plan", {"text": args.text, "lang": args.lang}, opener)
    if args.cmd == "revise":
        body = {
            "intent": args.intent,
            "day": args.day,
            "place_id": args.place_id,
            "city": args.city,
            "mode": args.mode,
            "lang": args.lang,
        }
        body = {k: v for k, v in body.items() if v is not None}
        plan_id = urllib.parse.quote(args.plan_id, safe="")
        return stream_plan(f"/plan/{plan_id}/revise", body, opener)
    if args.cmd == "compare":
        body = {
            "origin": args.origin,
            "destination": args.destination,
            "date": args.on,
            "rank_by": args.rank_by,
            "travellers": args.travellers,
        }
        return get_json("POST", "/routes/compare", {k: v for k, v in body.items() if v}, opener)
    if args.cmd == "katha":
        body = {
            "subject_kind": args.kind,
            "subject": args.subject,
            "length_min": args.minutes,
            "lang": args.lang,
        }
        return get_json("POST", "/guide/katha", body, opener)
    if args.cmd == "ask":
        body = {"question": args.question, "lang": args.lang, "lat": args.lat, "lng": args.lng}
        return get_json(
            "POST", "/guide/ask", {k: v for k, v in body.items() if v is not None}, opener
        )
    if args.cmd == "pnr":
        return get_json(
            "GET", "/routes/pnr-mock?" + urllib.parse.urlencode({"pnr": args.pnr}), None, opener
        )
    raise ValueError(args.cmd)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ty.py", description="Travel Yantra API for agents")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("plan", help="plan a trip from free text")
    s.add_argument("text")
    s.add_argument("--lang", choices=LANGS, default="en")

    s = sub.add_parser("revise", help="revise a plan by its plan_id")
    s.add_argument("plan_id")
    s.add_argument("intent", choices=["lighter_day", "swap_stop", "rain", "move_day", "transport"])
    s.add_argument("--day", help="YYYY-MM-DD; lighter_day needs it, rain is optional")
    s.add_argument("--place-id", help="swap_stop: a stop id from the itinerary")
    s.add_argument("--city", help="move_day: the destination that gains a day")
    s.add_argument("--mode", choices=["road", "rail", "air"], help="transport: the new mode")
    s.add_argument("--lang", choices=LANGS, default="en")

    s = sub.add_parser("compare", help="compare road, rail and air between two cities")
    s.add_argument("origin")
    s.add_argument("destination")
    s.add_argument("--on", help="YYYY-MM-DD")
    s.add_argument("--rank-by", choices=["balanced", "time", "cost", "changes"], default="balanced")
    s.add_argument("--travellers", type=int, default=1)

    s = sub.add_parser("katha", help="the story of a place, a city or a day")
    s.add_argument("subject")
    s.add_argument("--kind", choices=["place", "city"], default="place")
    s.add_argument("--minutes", type=int, choices=[2, 5, 10], default=2)
    s.add_argument("--lang", choices=LANGS, default="en")

    s = sub.add_parser("ask", help="ask the travel guide (history, food, emergencies)")
    s.add_argument("question")
    s.add_argument("--lang", choices=LANGS, default="en")
    s.add_argument("--lat", type=float)
    s.add_argument("--lng", type=float)

    s = sub.add_parser("pnr", help="track a sample PNR (mock data)")
    s.add_argument("pnr")
    return p


def main(argv: list[str] | None = None, opener=None) -> int:
    args = parser().parse_args(argv)
    try:
        out, code = run(args, opener), 0
    except ApiError as e:
        out, code = {"error": str(e)}, 1
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
