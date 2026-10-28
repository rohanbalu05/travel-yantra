"""P9 day shape: a travel-only day says so, stops are grouped by area, lunch has its gap, and nothing is
listed on a day the journey leaves no time for."""

import json
from datetime import date, datetime, time, timedelta

from fastapi.testclient import TestClient

from core import fakes
from core.checker import check
from core.solver import (
    CLUSTER_MIN,
    LUNCH_FROM,
    LUNCH_UNTIL,
    Travel,
    build_day,
    hop_of,
    limits,
    schedule,
)
from main import app
from ty_contracts import Itinerary, Leg, Mode, Place

client = TestClient(app)
GOA = fakes.sample("goa_family.json").request


def final(body) -> Itinerary:
    lines = client.post("/plan", json=body.model_dump(mode="json")).text.splitlines()
    return Itinerary.model_validate([json.loads(x[6:]) for x in lines if x.startswith("data: ")][-1]["partial"])


def place(pid, mins, lat=15.50, lng=73.91, category="monument"):
    return Place(id=pid, name=pid, lat=lat, lng=lng, category=category, typical_visit_minutes=mins, source="test")


def test_an_overnight_train_day_is_a_travel_day_never_a_rest_day():
    it = final(GOA.model_copy(update={"transport_mode": Mode.rail}))
    first = it.days[0]
    hop = hop_of(first)
    assert hop.arrive.date() > first.date and first.stops == []
    word = f"Travel day: train {hop.ref}, {hop.depart:%H:%M} → {hop.arrive:%H:%M}"
    assert first.notes[0] == word and first.title.endswith(word)


def test_goa_days_keep_to_one_area_and_the_plan_is_clean():
    it = final(GOA)
    travel = Travel()
    for d in it.days:
        for a in d.stops:
            assert min((travel.minutes(a, b) for b in d.stops if b is not a), default=0) <= CLUSTER_MIN, d.title
    assert check(it) == [] and it.budget.within_budget is True


def test_lunch_is_a_gap_between_visits_in_the_window():
    lim = limits(GOA)
    day = date(2026, 12, 12)
    stops = [place("a", 180), place("b", 60, lat=15.51)]  # a ends 12:00 (09:00 start), b would start at ~12:05
    plan, problem = build_day(day, stops, Travel(), lim, reorder=False)
    assert problem is None
    a, b = plan.schedule
    gap = b.start - a.leave
    assert gap >= timedelta(minutes=45) and any(n.startswith("Lunch ") for n in plan.notes)
    lunch = next(n for n in plan.notes if n.startswith("Lunch "))
    assert LUNCH_FROM <= datetime.strptime(lunch[6:11], "%H:%M").time() <= LUNCH_UNTIL


def test_a_long_visit_over_midday_includes_lunch_and_a_food_stop_is_lunch():
    lim = limits(GOA)
    day = date(2026, 12, 12)
    visits, _ = schedule(day, [place("falls", 240)], [], lim)
    assert visits[0].lunch == datetime.combine(day, time(12, 30))
    assert visits[0].leave - visits[0].start == timedelta(minutes=240 + 45)
    food = place("thali", 45, category="food")
    visits, _ = schedule(day, [place("a", 120), food, place("b", 60)], [5, 5], lim)  # a: 10:00-12:00
    assert all(v.lunch is None for v in visits)


def test_the_checker_flags_stops_on_a_day_the_journey_arrives_too_late_for():
    lim = limits(GOA)
    night = Leg(**{"from": "Bengaluru"}, to="Goa", mode=Mode.rail, depart=datetime(2026, 12, 11, 15, 15),
                arrive=datetime(2026, 12, 12, 5, 47), minutes=872, cost_inr=2000, role="outbound", ref="17309")
    plan, _ = build_day(date(2026, 12, 11), [place("a", 60)], Travel(), lim, hop=night)
    it = fakes.sample("goa_family.json").model_copy(update={"days": [plan]})
    found = [v for v in check(it) if v.place_id == "a"]
    assert found and "arrives Sat 05:47, too late for visits that day" in found[0].message
