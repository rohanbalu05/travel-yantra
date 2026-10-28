"""TY-Bench scoring on the contracts' sample plan. No network, no model.

cd apps/api && uv run pytest ../../bench -q
"""

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench"))

from score import DIMS, meal_ok, score  # noqa: E402

SAMPLE = json.loads(
    (ROOT / "packages/contracts/samples/goa_family.json").read_text(encoding="utf-8")
)
PLAN = SAMPLE["itinerary"] if "itinerary" in SAMPLE else SAMPLE
REQUEST = PLAN["request"]


def test_sample_plan_scores_on_every_dimension():
    s = score(PLAN, REQUEST)
    assert s["valid"] and s["dates"]
    assert set(DIMS) <= set(s)
    assert s["violations"] is not None


def test_no_plan_and_junk_fail_everything():
    for plan in (None, {"days": "nope"}):
        s = score(plan, REQUEST)
        assert not any(s[d] for d in DIMS)


def test_scored_against_the_asked_request_not_the_plans_copy():
    plan = copy.deepcopy(PLAN)
    plan["request"]["constraints"]["budget_inr"] = (
        10**9
    )  # a plan can't raise its own budget
    tight = {**REQUEST, "constraints": {**REQUEST["constraints"], "budget_inr": 1000}}
    assert score(plan, tight)["budget"] is False


def test_missing_day_fails_dates():
    plan = copy.deepcopy(PLAN)
    plan["days"] = plan["days"][:-1]
    assert score(plan, REQUEST)["dates"] is False


def test_meal_check():
    from ty_contracts import DayPlan

    def day(stops, schedule):
        return DayPlan.model_validate(
            {"date": "2026-12-12", "stops": stops, "schedule": schedule}
        )

    def stop(i, cat="church"):
        return {
            "id": i,
            "name": i,
            "lat": 15.5,
            "lng": 73.9,
            "category": cat,
            "typical_visit_minutes": 60,
            "source": "sample",
        }

    def at(i, a, b):
        return {
            "place_id": i,
            "arrive": f"2026-12-12T{a}:00",
            "start": f"2026-12-12T{a}:00",
            "leave": f"2026-12-12T{b}:00",
        }

    full = day(
        [stop("a"), stop("b")], [at("a", "10:00", "13:00"), at("b", "13:10", "16:00")]
    )
    gap = day(
        [stop("a"), stop("b")], [at("a", "10:00", "12:30"), at("b", "13:30", "16:00")]
    )
    food = day(
        [stop("a"), stop("lunch", "restaurant")],
        [at("a", "10:00", "13:00"), at("lunch", "13:10", "16:00")],
    )
    assert not meal_ok(full)
    assert meal_ok(gap)
    assert meal_ok(food)
    assert meal_ok(day([], []))
