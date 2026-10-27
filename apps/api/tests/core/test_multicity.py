import json
from datetime import date

from fastapi.testclient import TestClient

from core import steps
from core.checker import budget, check
from core.revise import revise
from core.solver import city_of, hop_of, local_legs, out_of, split_days
from main import app
from ty_contracts import Itinerary, ReviseRequest, TripRequest, ViolationCode

client = TestClient(app)
TRIP = {"origin": "Bengaluru", "destinations": ["Mysuru", "Coorg"], "start_date": "2026-11-20", "end_date": "2026-11-24",
        "constraints": {"budget_inr": 80000, "pace": "balanced",
                        "travellers": [{"name": "Arjun Rao", "age": 34}, {"name": "Venkatesh", "age": 64}]}}


def plan(body=TRIP) -> Itinerary:
    events = [json.loads(line[6:]) for line in client.post("/plan", json=body).text.splitlines() if line.startswith("data: ")]
    assert events[-1]["stage"] == "done", events[-1]
    return Itinerary.model_validate(events[-1]["partial"])


def test_days_split_in_destination_order_earlier_cities_get_the_spare_day():
    r = TripRequest.model_validate(TRIP)
    assert [(c, len(d)) for c, d in split_days(r)] == [("Mysuru", 3), ("Coorg", 2)]
    three = r.model_copy(update={"destinations": ["Mysuru", "Coorg", "Hampi"]})
    assert [len(d) for _, d in split_days(three)] == [2, 2, 1]
    assert city_of(r, date(2026, 11, 23)) == "Coorg"


def test_each_city_gets_its_own_places_and_the_switch_day_opens_with_the_hop():
    it = plan()
    r = it.request
    mysuru = {p.id for p in steps.city_places(r, "Mysuru")}
    coorg = {p.id for p in steps.city_places(r, "Coorg")}
    for d in it.days:
        ids = {p.id for p in d.stops}
        assert ids <= (mysuru if city_of(r, d.date) == "Mysuru" else coorg)
    switch = it.days[3]
    hop = hop_of(switch)
    assert hop is not None and (hop.from_, hop.to) == ("Mysuru", "Coorg")
    assert switch.notes[0].startswith("Travel: Mysuru → Coorg")
    # Day 1 opens with the outbound journey, the last day closes with the journey home; no other journeys.
    assert hop_of(it.days[0]).from_ == "Bengaluru" and hop_of(it.days[0]).to == "Mysuru"
    assert out_of(it.days[-1]).from_ == "Coorg" and out_of(it.days[-1]).to == "Bengaluru"
    assert all(hop_of(d) is None for d in it.days[1:] if d.date != switch.date)
    assert all(out_of(d) is None for d in it.days[:-1])
    assert check(it) == []


def test_journeys_cost_money_but_only_local_road_time_counts_against_the_cap():
    it = plan()
    hop = hop_of(it.days[3])
    without = it.model_copy(deep=True)
    day = without.days[3]
    without.days[3] = day.model_copy(update={"legs": day.legs[1:], "notes": [n for n in day.notes if not n.startswith("Travel")]})
    assert budget(it).transport_inr - budget(without).transport_inr == hop.cost_inr * 2
    # A tight cap judges only stop-to-stop legs; the inter-city journey moves the day's start instead.
    tight = it.model_copy(deep=True)
    tight.request.constraints.max_travel_hours_per_day = 1
    local = sum(leg.minutes for leg in local_legs(tight.days[3]))
    flagged = any(v.code is ViolationCode.too_much_travel and v.day == it.days[3].date for v in check(tight))
    assert flagged == (local > 60)


def test_stays_are_per_city_and_a_city_without_data_is_flagged():
    it = plan()
    mysuru = [s for s in it.stays if s.check_in == date(2026, 11, 20)]
    assert mysuru and all(s.check_out == date(2026, 11, 23) for s in mysuru)  # 3 Mysuru nights
    coorg = [s for s in it.stays if s.check_in == date(2026, 11, 23)]
    # Coorg has 1 night (the last day is spent travelling home); either TY3 has stays for it, or we say so.
    assert all(s.check_out == date(2026, 11, 24) for s in coorg)
    assert bool(coorg) != ("No stays found yet for Coorg" in it.warnings)
    assert {s.check_in for s in it.stays} <= {date(2026, 11, 20), date(2026, 11, 23)}


def test_revise_keeps_the_hop_and_stays_in_the_city():
    it = plan()
    switch = it.days[3]
    out, _, _ = revise(it, ReviseRequest(intent="lighter_day", day=switch.date))
    assert hop_of(next(d for d in out.days if d.date == switch.date)) == hop_of(switch)
    coorg_ids = {p.id for p in steps.city_places(it.request, "Coorg")}
    for d in out.days:
        if city_of(it.request, d.date) == "Mysuru":
            assert not ({p.id for p in d.stops} & coorg_ids)
    rained, _, _ = revise(it, ReviseRequest(intent="rain", day=switch.date))
    assert hop_of(next(d for d in rained.days if d.date == switch.date)) == hop_of(switch)


def test_single_city_trips_are_unchanged():
    one = plan({**TRIP, "destinations": ["Mysuru"]})
    assert len(one.days) == 5 and hop_of(one.days[0]).from_ == "Bengaluru" and out_of(one.days[-1]).to == "Bengaluru"
    assert all(hop_of(d) is None for d in one.days[1:]) and all(out_of(d) is None for d in one.days[:-1])


def test_a_hop_arriving_after_the_day_ends_leaves_no_visits_that_day():
    from datetime import datetime, time

    from core.solver import after_hop, limits
    from ty_contracts import Leg

    lim = limits(TripRequest.model_validate(TRIP))
    late = Leg(**{"from": "Mysuru"}, to="Coorg", mode="rail", depart=datetime(2026, 11, 23, 21, 0),
               arrive=datetime(2026, 11, 24, 6, 0), minutes=540, cost_inr=500)
    assert after_hop(lim, late).start == lim.end
    morning = late.model_copy(update={"depart": datetime(2026, 11, 23, 8, 0), "arrive": datetime(2026, 11, 23, 10, 0),
                                      "minutes": 120})
    assert after_hop(lim, morning).start == time(10, 30)


def test_day_one_starts_after_arrival_and_the_last_day_ends_before_the_journey_home():
    from datetime import timedelta

    from core.solver import HOP_SETTLE_MIN, RETURN_BUFFER_MIN, Travel, limits, schedule

    it = plan()
    lim = limits(it.request)
    first, last = it.days[0], it.days[-1]
    arrive = hop_of(first).arrive + timedelta(minutes=HOP_SETTLE_MIN)
    leave_by = out_of(last).depart - timedelta(minutes=RETURN_BUFFER_MIN)
    travel = Travel()
    for day, check_visit in ((first, lambda v: v.start >= arrive), (last, lambda v: v.leave <= leave_by)):
        mins = [travel.minutes(a, b) for a, b in zip(day.stops, day.stops[1:])]
        from core.solver import frame

        visits, problem = schedule(day.date, day.stops, mins, frame(lim, hop_of(day), out_of(day)))
        assert problem is None and all(check_visit(v) for v in visits)
    # Journeys leave at or after the time asked for (real trains wait for their departure).
    from datetime import datetime, time

    # Rail journeys are real trains (first after 06:00 out; home after the visits); road keeps 08:00 / 18:00.
    out_floor = time(6, 0) if hop_of(first).mode.value == "rail" else time(8, 0)
    assert hop_of(first).depart >= datetime.combine(first.date, out_floor)
    if out_of(last).mode.value != "rail":
        assert out_of(last).depart >= datetime.combine(last.date, time(18, 0))
    assert any(n.startswith("Return: Coorg → Bengaluru") for n in last.notes)


def test_visits_past_the_departure_home_are_flagged():
    it = plan()
    last = it.days[-1]
    early = out_of(last).model_copy(update={"depart": out_of(last).depart.replace(hour=11)})
    late = it.model_copy(deep=True)
    late.days[-1] = last.model_copy(update={"legs": [*last.legs[:-1], early]})
    assert any(v.code is ViolationCode.long_day and "home leaves" in v.message for v in check(late)) == bool(last.stops)


def test_move_day_gives_a_city_a_day_from_its_neighbour_and_replans():
    it = plan()
    out, what, _ = revise(it, ReviseRequest(intent="move_day", city="Coorg"))
    assert what == "Moved a day from Mysuru to Coorg"
    assert any("earlier changes to this plan were replaced" in w for w in out.warnings)
    assert out.request.days_per_destination == [2, 3]
    assert [city_of(out.request, d.date) for d in out.days] == ["Mysuru"] * 2 + ["Coorg"] * 3
    switch = out.days[2]
    assert hop_of(switch).from_ == "Mysuru" and hop_of(switch).to == "Coorg"
    assert out_of(out.days[-1]).from_ == "Coorg"
    assert check(out) == []
    # And back again: Mysuru takes the day back from Coorg.
    back, what, _ = revise(out, ReviseRequest(intent="move_day", city="mysuru"))
    assert back.request.days_per_destination == [3, 2] and what == "Moved a day from Coorg to Mysuru"


def test_move_day_errors():
    import pytest

    from core.revise import ReviseError

    it = plan()
    with pytest.raises(ReviseError):
        revise(it, ReviseRequest(intent="move_day", city="Goa"))
    one = plan({**TRIP, "destinations": ["Mysuru"]})
    with pytest.raises(ReviseError):
        revise(one, ReviseRequest(intent="move_day", city="Mysuru"))
    short = plan({**TRIP, "end_date": "2026-11-21"})  # one day each: nothing to spare
    with pytest.raises(ReviseError):
        revise(short, ReviseRequest(intent="move_day", city="Coorg"))


def test_move_day_through_the_endpoint():
    events = [json.loads(line[6:]) for line in client.post("/plan", json=TRIP).text.splitlines() if line.startswith("data: ")]
    pid = events[-1]["plan_id"]
    r = client.post(f"/plan/{pid}/revise", json={"intent": "move_day", "city": "Coorg"})
    done = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")][-1]
    assert done["stage"] == "done" and done["partial"]["request"]["days_per_destination"] == [2, 3]
    assert client.post(f"/plan/{pid}/revise", json={"intent": "move_day", "city": "Paris"}).status_code == 422


def test_journeys_are_marked_by_role_and_rebuilds_keep_other_notes():
    from core.solver import Travel, limits, rebuild_day

    it = plan()
    assert [leg.role for d in it.days for leg in d.legs if leg.role] == ["outbound", "between", "home"]
    assert all(leg.role is None for d in it.days for leg in local_legs(d))
    # A note of the traveller's own that happens to start like ours survives a re-plan of the day.
    day = it.days[3]
    it.days[3] = day.model_copy(update={"notes": [*day.notes, "Travel: carry a rain jacket"]})
    rebuild_day(it, day.date, day.stops[:1], Travel(), limits(it.request))
    notes = it.days[3].notes
    assert "Travel: carry a rain jacket" in notes and hop_of(it.days[3]).role == "between"
    assert sum(n.startswith("Travel: Mysuru → Coorg") for n in notes) == 1


def test_plans_saved_before_leg_roles_still_have_their_journeys():
    it = plan()
    old = it.model_copy(deep=True)
    for d in old.days:
        d.legs = [leg.model_copy(update={"role": None}) for leg in d.legs]
    assert hop_of(old.days[0]).to == "Mysuru" and hop_of(old.days[3]).to == "Coorg"
    assert out_of(old.days[-1]).to == "Bengaluru" and hop_of(old.days[1]) is None
    assert budget(old) == budget(it)  # the outbound journey is not counted twice
