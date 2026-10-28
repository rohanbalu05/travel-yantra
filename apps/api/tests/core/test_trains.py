from datetime import date, datetime, time, timedelta

from core import steps
from core.solver import RETURN_BUFFER_MIN, limits
from ty_contracts import Mode, Pace, TripRequest

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
    assert out.depart == steps.morning_train(DEMO, "Bengaluru", "Mysuru", date(2026, 10, 31)).legs[0].depart
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


def test_opening_hours_are_filled_only_where_asked(monkeypatch):
    import guide.hours

    calls = []
    monkeypatch.setattr(guide.hours, "live_hours", lambda places, *a, **k: calls.append(len(places)) or places)
    steps.city_places(DEMO, "Mysuru")  # coordinates only (e.g. a road estimate): no Places lookup
    assert calls == []
    steps.city_places(DEMO, "Mysuru", hours=True)
    steps.replan(DEMO)
    assert len(calls) == 2 and all(n > 0 for n in calls)


def test_the_last_day_is_used_and_the_train_home_follows_the_last_visit():
    # QA #109: Sunday ended about 11:30 with the train home at 20:03.
    from core.solver import RETURN_BUFFER_MIN, RETURN_FILL_END, Travel, out_of, schedule

    it = steps.replan(DEMO)
    last = it.days[-1]
    home = out_of(last)
    travel = Travel()
    visits, _ = schedule(last.date, last.stops, [travel.minutes(a, b) for a, b in zip(last.stops, last.stops[1:])],
                         limits(DEMO))
    ends = visits[-1].leave
    assert ends.time() <= RETURN_FILL_END and home.mode.value == "rail"
    assert home.depart >= ends + timedelta(minutes=RETURN_BUFFER_MIN)
    earlier = [t for t in steps._trains("Mysuru", "Bengaluru", last.date, (ends + timedelta(minutes=RETURN_BUFFER_MIN)).time())]
    assert home.depart == earlier[0].legs[0].depart  # the first train from then, not the day's last
    assert home.depart - ends < timedelta(hours=3)


def test_a_ride_from_the_station_to_the_first_stop_and_a_time_for_every_stop():
    # QA #118: no transfer from the station to the first stop, and the first stop had no time.
    it = steps.replan(DEMO)
    first = it.days[0]
    out, ride = first.legs[0], first.legs[1]
    assert (out.role, ride.role) == ("outbound", "transfer")
    assert ride.from_ == "Mysuru" and ride.to == first.stops[0].name and ride.depart >= out.arrive
    for day in it.days:
        assert [s.place_id for s in day.schedule] == [p.id for p in day.stops]
        assert all(s.arrive <= s.start < s.leave for s in day.schedule)
    assert first.schedule[0].start >= ride.arrive


def test_rail_journeys_carry_the_train_number_when_routes_gives_one():
    it = steps.replan(DEMO)
    refs = [leg.ref for leg in (it.days[0].legs[0], it.days[-1].legs[-1])]
    assert all(r is None or (r.isdigit() and len(r) == 5) for r in refs)


def test_when_the_last_train_leaves_too_early_visits_are_dropped_to_catch_it(monkeypatch):
    from core.solver import out_of

    it = steps.replan(DEMO)
    last = it.days[-1]
    # A train leaving 30 min before the planned visits end.
    leave = (last.schedule[-1].leave - timedelta(minutes=30)).replace(second=0)
    early = out_of(last).model_copy(update={"depart": leave})
    monkeypatch.setattr(steps, "hop", lambda *a, **k: early)  # pretend this is the only train left
    steps.retime_home(it)
    kept = it.days[-1]
    assert out_of(kept).depart == early.depart and 0 < len(kept.stops) < len(last.stops)
    assert any(w.startswith("Dropped ") and f"to catch the {leave:%H:%M} rail home" in w for w in it.warnings)
    assert kept.schedule[-1].leave <= early.depart - timedelta(minutes=45)


def test_the_last_day_takes_one_more_stop_when_the_cap_would_end_it_early_but_not_on_relaxed():
    # HQ V3-AL: fill the last day to about 15:00-17:00; relaxed pace keeps its cap.
    from core.solver import limits, out_of

    balanced = steps.replan(DEMO)
    day = balanced.days[-1]
    assert len(day.stops) == limits(DEMO).max_stops + 1
    # The day is filled up to the journey home: the next real train leaves 45 min to 2 h 30 after the last visit.
    gap = out_of(day).depart - day.schedule[-1].leave
    assert timedelta(minutes=45) <= gap <= timedelta(hours=2, minutes=30)
    relaxed_req = DEMO.model_copy(update={"constraints": DEMO.constraints.model_copy(update={"pace": Pace.relaxed})})
    relaxed = steps.replan(relaxed_req)
    assert len(relaxed.days[-1].stops) <= limits(relaxed_req).max_stops
