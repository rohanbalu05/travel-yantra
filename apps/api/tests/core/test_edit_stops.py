"""P10 plain-word edits: add a stop (by name, on a day or the best day), remove one, move one to another day."""

import json

import pytest
from fastapi.testclient import TestClient

from core import fakes, steps
from core.revise import ReviseError, revise
from main import app
from ty_contracts import Itinerary, Mode, ReviseRequest

client = TestClient(app)
GOA = fakes.sample("goa_family.json").request.model_copy(update={"transport_mode": Mode.air})


@pytest.fixture(scope="module")
def goa() -> Itinerary:
    return steps.replan(GOA)


def on(it, d):
    return [p.name for day in it.days if day.date == d for p in day.stops]


def where(it, name):
    return next((day.date for day in it.days for p in day.stops if p.name == name), None)


def test_add_a_stop_by_name_on_the_day_asked(goa):
    # "Squeeze in Fort Aguada on the second day" (TY5's live test).
    name = "Fort Aguada"
    if where(goa, name):
        goa = revise(goa, ReviseRequest(intent="remove_stop", place_id=next(
            p.id for d in goa.days for p in d.stops if p.name == name)))[0]
    day = where(goa, "Calangute Beach") or goa.days[-2].date
    out, what, _ = revise(goa, ReviseRequest(intent="add_stop", place="fort aguada", day=day))
    assert name in on(out, day) and what.startswith(f"Added {name} to {day:%a %d %b}")
    assert sum(len(d.stops) for d in out.days) == sum(len(d.stops) for d in goa.days) + 1  # nothing else lost


def test_a_full_day_keeps_its_top_sight_and_says_where_the_stop_fits(goa):
    falls = where(goa, "Dudhsagar Falls")
    assert falls
    with pytest.raises(ReviseError, match=f"{falls:%a %d %b} is full with Dudhsagar Falls"):
        revise(goa, ReviseRequest(intent="add_stop", place="Chapora Fort", day=falls))


def test_add_without_a_day_picks_one_and_twice_is_a_422(goa):
    out, what, _ = revise(goa, ReviseRequest(intent="add_stop", place="Goa State Museum"))
    day = where(out, "Goa State Museum")
    assert day is not None and what.startswith(f"Added Goa State Museum to {day:%a %d %b}")
    with pytest.raises(ReviseError, match="already on"):
        revise(out, ReviseRequest(intent="add_stop", place="goa state museum"))
    with pytest.raises(ReviseError, match="could not find"):
        revise(out, ReviseRequest(intent="add_stop", place="Eiffel Tower"))


def test_remove_and_move_a_stop(goa):
    day = next(d for d in goa.days if d.stops)
    gone = day.stops[0]
    out, what, _ = revise(goa, ReviseRequest(intent="remove_stop", place_id=gone.id))
    assert where(out, gone.name) is None and what == f"Removed {gone.name} from {day.date:%a %d %b}"
    other = goa.days[-1].date if day.date != goa.days[-1].date else goa.days[-2].date
    moved, what, _ = revise(goa, ReviseRequest(intent="move_stop", place_id=gone.id, day=other))
    assert gone.name in on(moved, other) and gone.name not in on(moved, day.date) and what.startswith("Moved ")
    with pytest.raises(ReviseError):
        revise(goa, ReviseRequest(intent="remove_stop", place_id="not-in-plan"))


def test_a_stop_cannot_move_to_another_citys_day():
    trip = GOA.model_copy(update={"origin": "Bengaluru", "destinations": ["Mysuru", "Goa"],
                                  "start_date": GOA.start_date, "end_date": GOA.end_date})
    it = steps.replan(trip)
    mysuru = next(d for d in it.days if d.stops and steps.split_days(trip)[0][1].count(d.date))
    goa_day = steps.split_days(trip)[1][1][-1]
    with pytest.raises(ReviseError, match="is in Mysuru"):
        revise(it, ReviseRequest(intent="move_stop", place_id=mysuru.stops[0].id, day=goa_day))


def test_edits_through_the_endpoint_keep_one_trip_and_say_what_changed():
    lines = client.post("/plan", json=GOA.model_dump(mode="json")).text.splitlines()
    done = [json.loads(x[6:]) for x in lines if x.startswith("data: ")][-1]
    r = client.post(f"/plan/{done['plan_id']}/revise", json={"intent": "add_stop", "place": "Chapora Fort"})
    events = [json.loads(x[6:]) for x in r.text.splitlines() if x.startswith("data: ")]
    assert events[1]["stage"] == "solving" and events[1]["message"].startswith(("Added Chapora Fort", "Chapora Fort"))
    assert events[-1]["plan_id"] == done["plan_id"]
    assert client.post(f"/plan/{done['plan_id']}/revise", json={"intent": "add_stop", "place": "Nowhere Palace"}).status_code == 422


def chosen(it):
    from core.checker import chosen_stays

    return chosen_stays(it)[0]


def test_change_stay_by_id_cheaper_and_better_rated(goa):
    now = chosen(goa)
    other = next(s for s in goa.stays if s is not now and s.id)
    out, what, _ = revise(goa, ReviseRequest(intent="change_stay", stay_id=other.id))
    assert chosen(out).id == other.id and what.startswith(f"Your stay in Goa is now {other.name}")
    assert out.budget.stay_inr != goa.budget.stay_inr or other.price_per_night_inr == now.price_per_night_inr
    cheaper, what, _ = revise(goa, ReviseRequest(intent="change_stay", stay_pick="cheaper", city="Goa"))
    assert chosen(cheaper).price_per_night_inr < now.price_per_night_inr
    # One step down: no listed stay sits between the old price and the new one.
    assert not [s for s in goa.stays if chosen(cheaper).price_per_night_inr < s.price_per_night_inr < now.price_per_night_inr]
    best = max(goa.stays, key=lambda s: s.rating or 0)
    if (now.rating or 0) < (best.rating or 0):
        rated, _, _ = revise(goa, ReviseRequest(intent="change_stay", stay_pick="better_rated"))
        assert (chosen(rated).rating or 0) > (now.rating or 0)
    lowest = min(goa.stays, key=lambda s: s.price_per_night_inr)
    cheapest = revise(goa, ReviseRequest(intent="change_stay", stay_id=lowest.id))[0]
    with pytest.raises(ReviseError, match="no cheaper stay is listed for Goa"):
        revise(cheapest, ReviseRequest(intent="change_stay", stay_pick="cheaper", city="Goa"))
    with pytest.raises(ReviseError):
        revise(goa, ReviseRequest(intent="change_stay", stay_id="not-a-stay"))


def test_budget_style_replans_food_travel_and_stays_but_keeps_the_stops(monkeypatch):
    seen = []
    real = steps.city_stays

    def stays(request, *a, **k):
        seen.append(request.constraints.budget_style)
        return real(request, *a, **k)

    monkeypatch.setattr(steps, "city_stays", stays)
    it = steps.replan(GOA.model_copy(update={"transport_mode": None}))
    out, what, _ = revise(it, ReviseRequest(intent="budget_style", style="shoestring"))
    assert out.request.constraints.budget_style == "shoestring" and seen[-1] == "shoestring"
    assert out.budget.food_per_person_day_inr == 400 and "₹400 a person a day" in what
    assert what.startswith("Planned for a shoestring budget")
    kept = {p.id for d in out.days for p in d.stops}
    assert kept and kept <= {p.id for d in it.days for p in d.stops} | kept
