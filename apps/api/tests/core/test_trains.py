from datetime import date, datetime, time, timedelta

from core import steps
from core.solver import RETURN_BUFFER_MIN, limits
from ty_contracts import Mode, TripRequest

DEMO = TripRequest.model_validate({"origin": "Bengaluru", "destinations": ["Mysuru"], "start_date": "2026-10-31",
                                   "end_date": "2026-11-01"})


def test_the_morning_train_is_the_first_after_six_preferring_one_that_arrives_before_the_visits():
    trains = steps._trains("Bengaluru", "Mysuru", date(2026, 10, 31), time(6, 0))
    assert trains and all(t.legs[0].depart.time() >= time(6, 0) for t in trains)
    picked = steps.morning_train(DEMO, "Bengaluru", "Mysuru", date(2026, 10, 31))
    start = datetime.combine(date(2026, 10, 31), limits(DEMO).start)
    early = [t for t in trains if t.legs[-1].arrive <= start]
    assert picked == (early[0] if early else trains[0])


def test_the_evening_train_leaves_after_the_visits_and_gets_home_the_same_day():
    day = date(2026, 11, 1)
    picked = steps.evening_train(DEMO, "Mysuru", "Bengaluru", day)
    after = datetime.combine(day, limits(DEMO).end) + timedelta(minutes=RETURN_BUFFER_MIN)
    assert picked is not None and picked.mode.value == "rail"
    if picked.legs[0].depart >= after:
        later = steps._trains("Mysuru", "Bengaluru", day, after.time())
        same_day = [t for t in later if t.legs[-1].arrive.date() == day]
        assert picked == (same_day[-1] if same_day else later[0])


def test_the_demo_trip_rides_real_trains_both_ways():
    it = steps.replan(DEMO)
    out, home = it.days[0].legs[0], it.days[-1].legs[-1]
    assert (out.role, out.mode.value, home.role, home.mode.value) == ("outbound", "rail", "home", "rail")
    assert out.depart.time() >= time(6, 0) and out.depart.time() != time(8, 0)
    assert it.transport[0].legs[0].depart == out.depart  # the listed option is the train taken


def test_road_only_routes_keep_the_fixed_times():
    road = steps.timed(DEMO, "Mysuru", "Coorg", date(2026, 11, 23),
                       steps.transport_options(DEMO)[0].model_copy(update={"mode": Mode.road}), "between")
    assert road.mode.value == "road"  # not swapped for a train


def test_days_have_titles_and_journeys_read_like_a_timetable():
    it = steps.replan(DEMO)
    assert [d.title for d in it.days] == ["Day 1 · Sat 31 Oct · Arrive in Mysuru", "Day 2 · Sun 01 Nov · Mysuru, then home"]
    out, home = it.days[0].legs[0], it.days[-1].legs[-1]
    assert it.days[0].notes[0] == f"Train Bengaluru → Mysuru, {out.depart:%H:%M}–{out.arrive:%H:%M}, " \
                                  f"{out.minutes // 60}h{out.minutes % 60:02d}"
    assert it.days[-1].notes[-1].startswith(f"Train home Mysuru → Bengaluru, {home.depart:%H:%M}–")
