import json
from datetime import date

from fastapi.testclient import TestClient

from core import steps
from core.checker import budget, check
from core.revise import revise
from core.solver import city_of, hop_of, split_days
from main import app
from ty_contracts import Itinerary, ReviseRequest, TripRequest, ViolationCode

client = TestClient(app)
TRIP = {"origin": "Bengaluru", "destinations": ["Mysuru", "Coorg"], "start_date": "2026-11-20", "end_date": "2026-11-24",
        "constraints": {"budget_inr": 40000, "pace": "balanced",
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
    assert all(hop_of(d) is None for d in it.days if d.date != switch.date)
    assert check(it) == []


def test_the_hop_counts_as_road_time_and_money():
    it = plan()
    hop = hop_of(it.days[3])
    without = it.model_copy(deep=True)
    without.days[3] = without.days[3].model_copy(update={"legs": without.days[3].legs[1:]})
    assert budget(it).transport_inr - budget(without).transport_inr == hop.cost_inr * 2
    # A tight travel cap makes the hop alone too much for that day.
    tight = it.model_copy(deep=True)
    tight.request.constraints.max_travel_hours_per_day = 1
    assert any(v.code is ViolationCode.too_much_travel and v.day == it.days[3].date for v in check(tight))


def test_stays_are_per_city_and_a_city_without_data_is_flagged():
    it = plan()
    assert {s.check_in for s in it.stays} == {date(2026, 11, 20)}  # Mysuru stays; no Coorg data yet
    assert all(s.check_out == date(2026, 11, 23) for s in it.stays)
    assert "No stays found yet for Coorg" in it.warnings


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
    assert all(hop_of(d) is None for d in one.days) and len(one.days) == 5


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
