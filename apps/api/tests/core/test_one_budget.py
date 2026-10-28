"""P9: one budget (each option's whole-trip total is the total after switching), the default mode weighs
door-to-door time against the trip's length, and real users never get sample data."""

import json

import pytest
from fastapi.testclient import TestClient

from core import fakes, steps
from core.steps import pick_mode
from main import app
from ty_contracts import Itinerary, Leg, Mode, TransportOption, TripRequest

client = TestClient(app)
GOA = fakes.sample("goa_family.json").request
MYSURU = fakes.sample("mysuru_weekend.json").request


def frames(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def option(mode: Mode, minutes: int, cost: int) -> TransportOption:
    leg = Leg(**{"from": "A"}, to="B", mode=mode, depart="2026-12-11T08:00", arrive="2026-12-11T08:00",
              minutes=0, cost_inr=cost)
    return TransportOption(mode=mode, legs=[leg], total_minutes=minutes, total_cost_inr=cost, comfort=3)


def trip(days: int, style=None, mode=None) -> TripRequest:
    end = GOA.start_date.replace(day=GOA.start_date.day + days - 1)
    c = GOA.constraints.model_copy(update={"budget_style": style, "budget_inr": None})
    return GOA.model_copy(update={"end_date": end, "constraints": c, "transport_mode": mode})


GOA_WAYS = [option(Mode.rail, 956, 1500), option(Mode.road, 660, 4000), option(Mode.air, 180, 19000)]


def test_a_short_trip_flies_rather_than_spend_two_days_on_the_train():
    mode, why = pick_mode(trip(3), GOA_WAYS)
    assert mode is Mode.air
    assert why == ("Flight: the train costs less but takes 15h56 each way, too much of a 3-day trip; "
                   "the flight takes 3h00 door to door.")


def test_a_long_trip_or_a_shoestring_one_takes_the_cheap_train():
    assert pick_mode(trip(10), GOA_WAYS)[0] is Mode.rail
    mode, why = pick_mode(trip(6, "shoestring"), GOA_WAYS)
    assert mode is Mode.rail and why.startswith("Train: the cheapest way")


def test_luxury_takes_the_quickest_and_a_chosen_mode_is_kept():
    assert pick_mode(trip(10, "luxury"), GOA_WAYS) == (Mode.air, "Flight: the quickest way, 3h00 door to door, "
                                                                 "for a luxury trip.")
    assert pick_mode(trip(3, mode=Mode.rail), GOA_WAYS) == (None, None)


def test_a_weekend_drive_is_fair_so_the_cheapest_fair_way_wins():
    ways = [option(Mode.rail, 150, 600), option(Mode.road, 180, 2400)]
    mode, why = pick_mode(trip(2), ways)
    assert mode is Mode.rail and why == "Train: the cheapest way that keeps travel to a fair part of a 2-day trip (2h30 each way)."


@pytest.mark.parametrize("body", [MYSURU, GOA], ids=["mysuru", "goa"])
def test_each_option_total_is_the_total_after_switching_to_it(body):
    done = frames(client.post("/plan", json=body.model_dump(mode="json")))[-1]
    switched = 0
    for mode in sorted({o.mode for o in Itinerary.model_validate(done["partial"]).transport}):
        # The numbers the Options screen shows now, on the plan as it is now.
        it = Itinerary.model_validate(client.get(f"/plan/{done['plan_id']}").json()["itinerary"])
        in_use = next(o for o in it.transport if o.mode is it.days[0].legs[0].mode)
        assert in_use.trip_total_inr == it.budget.total_inr
        if mode is in_use.mode:
            continue
        listed = next(o for o in it.transport if o.mode is mode).trip_total_inr
        r = client.post(f"/plan/{done['plan_id']}/revise", json={"intent": "transport", "mode": mode.value})
        if r.status_code == 422:
            assert listed is None
            continue
        after = Itinerary.model_validate(frames(r)[-1]["partial"])
        assert after.budget.total_inr == listed and after.transport_reason is None
        switched += 1
    assert switched


def test_the_budget_counts_the_home_journey_and_getting_around():
    it = Itinerary.model_validate(frames(client.post("/plan", json=MYSURU.model_dump(mode="json")))[-1]["partial"])
    journeys = [leg for d in it.days for leg in d.legs if leg.role in ("outbound", "between", "home")]
    assert {leg.role for leg in journeys} >= {"outbound", "home"}
    b = it.budget
    assert b.transport_inr == sum(leg.cost_inr for leg in journeys) and b.local_transport_inr > 0
    assert b.total_inr == b.transport_inr + b.local_transport_inr + b.stay_inr + b.activities_inr + b.food_inr


def test_real_users_never_get_sample_places_options_or_stays(monkeypatch):
    monkeypatch.delenv("TY_SAMPLE_DATA")
    monkeypatch.setattr("guide.planner.places_for", lambda *a, **k: [])
    assert steps.city_places(GOA, "Goa") == []
    monkeypatch.setattr(steps, "_compared", lambda *a, **k: ())
    assert steps.transport_options(GOA) == []
    monkeypatch.setattr("routes.stays.rank_stays", lambda *a, **k: [])
    assert steps.city_stays(GOA, "Goa", GOA.start_date, 3) == []
    monkeypatch.setenv("TY_SAMPLE_DATA", "1")
    assert steps.city_places(GOA, "Goa") and steps.transport_options(GOA) and steps.city_stays(GOA, "Goa", GOA.start_date, 3)


def test_the_budget_style_reaches_routes_for_rail_class_and_stays(monkeypatch):
    seen = {}

    def rank(city, check_in, check_out, **kw):
        seen.update(kw)
        return []

    monkeypatch.setattr("routes.stays.rank_stays", rank)
    lux = GOA.model_copy(update={"constraints": GOA.constraints.model_copy(update={"budget_style": "luxury"})})
    steps.city_stays(lux, "Goa", GOA.start_date, 2)
    assert seen["budget_style"] == "luxury" and seen["limit"] == 5
    assert steps.routes_style(GOA) is None and steps.routes_style(trip(3, "shoestring")) == "budget"
