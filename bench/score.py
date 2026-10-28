"""Scores one plan for TY-Bench. Pure: no network, no model.

Dimensions, each pass or fail:
  valid        parses as a ty_contracts Itinerary (anything else fails every dimension)
  dates        one day per date from start_date to end_date, in order
  hours        TY1's checker: no stop outside its opening hours ("closed")
  travel_time  TY1's checker: no day over the traveller's road-time limit ("too_much_travel")
  constraints  TY1's checker: no day too long ("long_day") and rest for elders ("no_rest")
  budget       TY1's checker: total from core.checker.budget within the request's budget
  meals        the bench's own check (TY1's checker has none): every day with stops
               has a food stop, or 45 free minutes between 12:00 and 14:30
"""

from __future__ import annotations

import sys
from datetime import datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

FOOD = (
    "food",
    "restaurant",
    "cafe",
    "café",
    "meal",
    "lunch",
    "eatery",
    "dhaba",
    "thali",
)
LUNCH = (time(12, 0), time(14, 30))
LUNCH_MIN = 45

CODES = {
    "hours": {"closed"},
    "travel_time": {"too_much_travel"},
    "constraints": {"long_day", "no_rest"},
    "budget": {"over_budget"},
}
DIMS = ["valid", "dates", "hours", "travel_time", "meals", "budget", "constraints"]


def _fail(reason: str) -> dict:
    return {
        **{d: False for d in DIMS},
        "violations": None,
        "codes": [],
        "reason": reason,
    }


def dates_ok(it) -> bool:
    r = it.request
    want = [
        r.start_date + timedelta(days=i)
        for i in range((r.end_date - r.start_date).days + 1)
    ]
    return [d.date for d in it.days] == want


def _busy(day) -> list[tuple[datetime, datetime]]:
    """Busy spans: each stop's visit and each ride, from the day's schedule and legs."""
    spans = [(s.arrive, s.leave) for s in day.schedule]
    spans += [(leg.depart, leg.arrive) for leg in day.legs]
    if not day.schedule:
        # No schedule: stops back to back from 9:00 with their usual visit lengths.
        t = datetime.combine(day.date, time(9, 0))
        for p in day.stops:
            spans.append((t, t + timedelta(minutes=p.typical_visit_minutes)))
            t += timedelta(minutes=p.typical_visit_minutes)
    return [(a.replace(tzinfo=None), b.replace(tzinfo=None)) for a, b in spans if b > a]


def meal_ok(day) -> bool:
    if not day.stops:
        return True
    if any(
        any(w in (p.category or "").lower() or w in p.name.lower() for w in FOOD)
        for p in day.stops
    ):
        return True
    lo, hi = (datetime.combine(day.date, t) for t in LUNCH)
    free, t = 0, lo
    for a, b in sorted(_busy(day)):
        if b <= t or a >= hi:
            continue
        if a > t:
            free = max(free, (min(a, hi) - t).total_seconds() / 60)
        t = max(t, b)
        if t >= hi:
            break
    if t < hi:
        free = max(free, (hi - t).total_seconds() / 60)
    return free >= LUNCH_MIN


def score(plan: dict | None, request: dict) -> dict:
    from core.checker import check
    from ty_contracts import Itinerary, TripRequest

    if plan is None:
        return _fail("no plan")
    try:
        it = Itinerary.model_validate(plan)
    except Exception as e:  # noqa: BLE001 - any validation error is an invalid plan
        return _fail(f"invalid: {str(e).splitlines()[0][:160]}")
    asked = TripRequest.model_validate(request)
    # Score against what was asked, not what the plan says was asked.
    it = it.model_copy(update={"request": asked})
    try:
        violations = check(it)
    except Exception as e:  # noqa: BLE001 - a plan the checker can't read fails the checker's dimensions
        out = _fail(f"checker: {type(e).__name__}: {e}")
        out.update(
            valid=True, dates=dates_ok(it), meals=all(meal_ok(d) for d in it.days)
        )
        return out
    codes = sorted(
        {v.code.value if hasattr(v.code, "value") else str(v.code) for v in violations}
    )
    out = {
        "valid": True,
        "dates": dates_ok(it),
        "meals": all(meal_ok(d) for d in it.days),
        "violations": len(violations),
        "codes": codes,
        "reason": None,
    }
    for dim, cs in CODES.items():
        out[dim] = not (set(codes) & cs)
    return out


if __name__ == "__main__":
    # Score a results file again, e.g. after the checker changes: python score.py results/x.jsonl
    import json

    reqs = {
        json.loads(x)["id"]: json.loads(x)["request"]
        for x in (Path(__file__).parent / "requests.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if x.strip()
    }
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        print(r["id"], r["arm"], score(r.get("plan"), reqs[r["id"]]))
