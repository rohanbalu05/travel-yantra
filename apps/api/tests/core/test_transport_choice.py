import json

from fastapi.testclient import TestClient

from core import steps
from core.revise import ReviseError, revise
from core.solver import hop_of, out_of
from main import app
from ty_contracts import Itinerary, Mode, ReviseRequest, TripRequest

client = TestClient(app)
DEMO = {"origin": "Bengaluru", "destinations": ["Mysuru"], "start_date": "2026-10-31", "end_date": "2026-11-01"}


def done(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")][-1]


def journeys(it: Itinerary):
    return [leg for d in it.days for leg in (hop_of(d), out_of(d)) if leg]


def test_a_new_plan_with_road_chosen_goes_by_road_both_ways():
    it = steps.replan(TripRequest.model_validate({**DEMO, "transport_mode": "road"}))
    assert it.request.transport_mode is Mode.road and it.transport[0].mode is Mode.road
    assert [(j.role, j.mode) for j in journeys(it)] == [("outbound", Mode.road), ("home", Mode.road)]
    assert it.days[0].notes[0].startswith("Drive Bengaluru → Mysuru")


def test_without_a_choice_the_best_ranked_option_is_used():
    it = steps.replan(TripRequest.model_validate(DEMO))
    assert it.request.transport_mode is None and journeys(it)[0].mode is it.transport[0].mode


def test_revise_switches_every_journey_and_keeps_the_stops():
    by_train = steps.replan(TripRequest.model_validate({**DEMO, "transport_mode": "rail"}))
    assert {j.mode for j in journeys(by_train)} == {Mode.rail}
    by_road, what, _ = revise(by_train, ReviseRequest(intent="transport", mode="road"))
    assert what == "Switched every journey to road"
    assert by_road.request.transport_mode is Mode.road and by_road.transport[0].mode is Mode.road
    assert {j.mode for j in journeys(by_road)} == {Mode.road}
    # Stops are kept; one that no longer fits the later arrival is moved to another day or dropped with a warning.
    before = {p.id: p.name for d in by_train.days for p in d.stops}
    after = {p.id for d in by_road.days for p in d.stops}
    dropped = [name for pid, name in before.items() if pid not in after]
    assert after <= set(before) and all(any(n in w for w in by_road.warnings) for n in dropped)
    assert by_road.budget.transport_inr != by_train.budget.transport_inr  # the journeys changed, so did the cost


def test_switch_through_the_endpoint_and_a_mode_the_trip_does_not_have():
    first = done(client.post("/plan", json=DEMO))
    r = client.post(f"/plan/{first['plan_id']}/revise", json={"intent": "transport", "mode": "road"})
    after = done(r)
    it = Itinerary.model_validate(after["partial"])
    assert after["stage"] == "done" and it.request.transport_mode == "road"
    assert it.days[0].legs[0].mode == "road" and it.days[-1].legs[-1].mode == "road"
    has_air = any(o.mode is Mode.air for o in steps.transport_options(TripRequest.model_validate(DEMO)))
    air = client.post(f"/plan/{first['plan_id']}/revise", json={"intent": "transport", "mode": "air"})
    assert air.status_code == (200 if has_air else 422)
    try:
        revise(Itinerary.model_validate(first["partial"]), ReviseRequest(intent="transport", mode="air"))
        assert has_air
    except ReviseError:
        assert not has_air


def test_a_journey_without_the_chosen_mode_is_named_in_a_warning(monkeypatch):
    by_train = steps.replan(TripRequest.model_validate({**DEMO, "transport_mode": "rail"}))
    real_hop = steps.hop

    def no_rail_home(request, a, b, day, *args, **kw):  # pretend the way home has no train
        leg = real_hop(request, a, b, day, *args, **kw)
        return leg.model_copy(update={"mode": Mode.road}) if kw.get("role") == "home" else leg

    monkeypatch.setattr(steps, "hop", no_rail_home)
    out, what, _ = revise(by_train, ReviseRequest(intent="transport", mode="rail"))
    assert what == "Switched journeys to train where possible"
    assert any(w.startswith("No train between Mysuru and Bengaluru") for w in out.warnings)
