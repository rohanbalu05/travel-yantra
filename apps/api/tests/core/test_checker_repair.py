from datetime import date, time

from core import fakes
from core.checker import budget, check
from core.repair import MAX_ROUNDS, check_and_repair, repair
from core.solver import REST_NOTE, Travel, build_day, limits, solve
from ty_contracts import DayPlan, Itinerary, OpeningHours, Pace, Place, ViolationCode

GOA = fakes.sample("goa_family.json")
GOA_PLACES = [p for d in GOA.days for p in d.stops]


def solved(request=GOA.request, places=GOA_PLACES, **update) -> Itinerary:
    days, _ = solve(request, places)
    it = GOA.model_copy(update={"request": request, "days": days, "warnings": [], **update}, deep=True)
    it.budget = budget(it)
    return it


def with_constraints(request, **c):
    return request.model_copy(update={"constraints": request.constraints.model_copy(update=c)})


def codes(it):
    return [v.code for v in check(it)]


def place(pid, mins, lat=15.50, lng=73.91, hours=None):
    return Place(id=pid, name=pid, lat=lat, lng=lng, category="x", typical_visit_minutes=mins,
                 opening_hours=hours or [], source="test")


def test_budget_matches_the_goa_sample():
    assert budget(GOA) == GOA.budget.model_copy(update={"within_budget": True})


def test_a_solved_goa_plan_is_clean():
    assert codes(solved()) == []


def test_over_budget_is_repaired_by_the_cheaper_option():
    air_first = list(reversed(GOA.transport))
    it = solved(transport=air_first)
    assert codes(it) == [ViolationCode.over_budget]
    fixed, rounds = check_and_repair(it)
    assert codes(fixed) == [] and rounds == 1
    assert fixed.transport[0].mode.value == "rail" and fixed.budget.within_budget is True


def test_closed_venue_moves_to_a_day_it_is_open():
    monday_only = place("mon-only", 60, hours=[OpeningHours(day="mon", opens=time(10), closes=time(16))])
    it = solved()
    friday = it.days[0]
    it.days[0] = build_day(friday.date, [*friday.stops, monday_only], Travel(), limits(it.request), reorder=False)[0]
    assert ViolationCode.closed in codes(it)
    fixed, _ = check_and_repair(it)
    assert codes(fixed) == []
    where = {p.id: d.date for d in fixed.days for p in d.stops}
    assert where["mon-only"] == date(2026, 12, 14)  # 14 Dec 2026 is a Monday


def test_ten_hour_day_is_repaired():
    req = with_constraints(GOA.request, pace=Pace.packed, travellers=[], max_travel_hours_per_day=8)
    long = [place(f"long{i}", 150, 15.50 + i * 0.01, 73.91) for i in range(5)]
    it = solved(req, GOA_PLACES)
    it.days[1] = DayPlan(date=it.days[1].date, stops=long)  # 12.5 hours of visits, no legs
    assert ViolationCode.long_day in codes(it)
    fixed, rounds = check_and_repair(it)
    assert ViolationCode.long_day not in codes(fixed) and rounds <= MAX_ROUNDS
    assert sum(len(d.stops) for d in fixed.days) >= len(GOA_PLACES)  # moved or dropped, never lost silently
    dropped = [w for w in fixed.warnings if w.startswith("Dropped")]
    planned = {p.id for d in fixed.days for p in d.stops}
    assert all(f"long{i}" in planned or any(f"long{i}" in w for w in dropped) for i in range(5))


def test_unrepairable_stops_after_three_rounds_with_warnings():
    it = solved(with_constraints(GOA.request, budget_inr=5000))
    fixed, rounds = check_and_repair(it)
    assert rounds == MAX_ROUNDS
    assert ViolationCode.over_budget in codes(fixed)
    assert any("over the ₹5,000 budget" in w for w in fixed.warnings)


def test_elderly_day_without_rest_is_flagged_and_replanned():
    req = with_constraints(GOA.request, pace=Pace.balanced)
    stops = [place("a", 150, 15.50, 73.91), place("b", 150, 15.51, 73.91), place("c", 120, 15.52, 73.91)]
    it = solved(req)
    it.days[2] = DayPlan(date=it.days[2].date, stops=stops)
    assert ViolationCode.no_rest in codes(it)
    fixed, _ = repair(it, check(it))
    assert ViolationCode.no_rest not in codes(fixed)
    assert REST_NOTE in fixed.days[2].notes or len(fixed.days[2].stops) < 3

