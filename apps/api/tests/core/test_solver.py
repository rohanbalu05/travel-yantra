import random
from datetime import date, datetime, time

from core import fakes
from core.solver import (
    WEEKDAYS,
    Travel,
    hours_on,
    limits,
    nearest_neighbour,
    schedule,
    solve,
    tour_minutes,
    two_opt,
)
from ty_contracts import OpeningHours, Pace, Place

GOA = fakes.sample("goa_family.json")
GOA_PLACES = [p for d in GOA.days for p in d.stops]


def place(pid, lat, lng, mins=60, hours=None):
    return Place(id=pid, name=pid, lat=lat, lng=lng, category="x", typical_visit_minutes=mins,
                 opening_hours=hours or [], source="test")


def with_pace(request, pace, **extra):
    c = request.constraints.model_copy(update={"pace": pace, **extra})
    return request.model_copy(update={"constraints": c})


def test_two_opt_never_lengthens_a_tour():
    rng = random.Random(7)
    travel = Travel()
    for trial in range(40):
        pts = [place(f"p{trial}-{i}", 15.3 + rng.random() * 0.4, 73.8 + rng.random() * 0.4) for i in range(rng.randint(2, 8))]
        for start in (pts, nearest_neighbour(pts, travel)):
            better = two_opt(start, travel)
            assert sorted(p.id for p in better) == sorted(p.id for p in start)
            assert tour_minutes(better, travel) <= tour_minutes(start, travel)


def test_two_opt_untangles_a_crossed_path():
    a, b, c, d = place("a", 15.0, 74.0), place("b", 15.0, 74.2), place("c", 15.2, 74.0), place("d", 15.2, 74.2)
    travel = Travel()
    crossed = [a, d, b, c]
    assert tour_minutes(two_opt(crossed, travel), travel) < tour_minutes(crossed, travel)


def test_no_stop_is_scheduled_outside_its_opening_hours():
    only_monday = place("mon-only", 15.50, 73.91, 60, [OpeningHours(day="mon", opens=time(10), closes=time(12))])
    late = place("late", 15.49, 73.83, 120, [OpeningHours(day=d, opens=time(16), closes=time(17)) for d in WEEKDAYS])
    days, left = solve(GOA.request, [*GOA_PLACES, only_monday, late])
    lim = limits(GOA.request)
    travel = Travel()
    for day in days:
        mins = [travel.minutes(a, b) for a, b in zip(day.stops, day.stops[1:])]
        visits, problem = schedule(day.date, day.stops, mins, lim)
        assert problem is None and len(visits) == len(day.stops)
        for v in visits:
            opens, closes = hours_on(v.place, day.date)
            assert datetime.combine(day.date, opens) <= v.start and v.leave <= datetime.combine(day.date, closes)
    # 11-14 Dec 2026 is Fri-Mon: the Monday-only stop can only land on the 14th.
    placed = {p.id: d.date for d in days for p in d.stops}
    assert placed.get("mon-only", date(2026, 12, 14)) == date(2026, 12, 14)
    assert "late" in {p.id for p in left}  # a 2-hour visit cannot fit a 1-hour window


# Planners return more candidates than a trip can hold; four more sample Goa stops make pace the limit.
GOA_MORE = [*GOA_PLACES, place("goa-aguada", 15.4920, 73.7735, 60), place("goa-reis", 15.4985, 73.8090, 45),
            place("goa-dona-paula", 15.4553, 73.8044, 45), place("goa-panjim-church", 15.4989, 73.8278, 30)]


def test_relaxed_pace_has_fewer_stops_per_day_than_balanced_on_goa():
    relaxed, _ = solve(GOA.request, GOA_MORE)
    balanced, _ = solve(with_pace(GOA.request, Pace.balanced), GOA_MORE)
    assert GOA.request.constraints.pace is Pace.relaxed
    assert max(len(d.stops) for d in relaxed) < max(len(d.stops) for d in balanced)
    assert all(len(d.stops) <= 2 for d in relaxed)


def test_a_short_list_spreads_over_the_trip():
    mysuru = fakes.sample("mysuru_weekend.json")
    days, left = solve(mysuru.request, [p for d in mysuru.days for p in d.stops])
    assert [len(d.stops) for d in days] == [2, 1] and not left


def test_every_goa_place_is_planned_once_with_legs_between_stops():
    days, left = solve(GOA.request, GOA_PLACES)
    ids = [p.id for d in days for p in d.stops]
    assert sorted(ids) == sorted(p.id for p in GOA_PLACES) and not left
    assert [d.date for d in days] == [date(2026, 12, 11 + i) for i in range(4)]
    for d in days:
        assert len(d.legs) == max(len(d.stops) - 1, 0)
        assert all(leg.arrive >= leg.depart for leg in d.legs)


def test_elderly_travellers_get_a_shorter_day_and_less_road_time():
    young = with_pace(GOA.request, Pace.balanced, travellers=[])
    assert limits(young).max_travel_min == 240 and not limits(young).rest
    old = limits(with_pace(GOA.request, Pace.balanced))
    assert old.rest and old.max_travel_min == 180 and old.end <= time(18)
