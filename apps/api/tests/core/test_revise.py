import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from core import fakes
from core.checker import budget, check
from core.revise import INDOOR, ReviseError, revise
from core.solver import solve
from main import app
from ty_contracts import Itinerary, ReviseRequest

client = TestClient(app)
GOA = fakes.sample("goa_family.json")


def goa_plan() -> Itinerary:
    days, _ = solve(GOA.request, fakes.places(GOA.request))
    it = GOA.model_copy(update={"days": days, "warnings": []}, deep=True)
    it.budget = budget(it)
    return it


def ids(it, d=None):
    return [p.id for day in it.days if d is None or day.date == d for p in day.stops]


def test_lighter_day_has_fewer_stops_and_passes_the_checker():
    it = goa_plan()
    busiest = max(it.days, key=lambda d: len(d.stops))
    out, what, _ = revise(it, ReviseRequest(intent="lighter_day", day=busiest.date))
    assert len(ids(out, busiest.date)) == len(busiest.stops) - 1
    assert check(out) == [] and what.startswith(("Moved", "Dropped"))
    assert sorted(ids(out)) == sorted(ids(it)) or any("Dropped" in w for w in out.warnings)


def test_swap_stop_replaces_it_with_a_place_not_already_planned():
    it = goa_plan()
    out, what, _ = revise(it, ReviseRequest(intent="swap_stop", place_id="goa-fontainhas"))
    assert "goa-fontainhas" not in ids(out) and what.startswith("Swapped Fontainhas")
    new = (set(ids(out)) - set(ids(it))).pop()
    assert new in {p.id for p in fakes.alternatives(GOA.request)}
    assert len(ids(out)) == len(ids(it)) and check(out) == []


def test_rain_moves_every_stop_indoors_and_passes_the_checker():
    it = goa_plan()
    assert any(p.category not in INDOOR for d in it.days for p in d.stops)  # Miramar beach, Fontainhas walk
    out, what, _ = revise(it, ReviseRequest(intent="rain"))
    assert all(p.category in INDOOR for d in out.days for p in d.stops)
    assert what.startswith("Rain plan:") and check(out) == []


def test_rain_on_one_day_leaves_the_other_days_alone():
    it = goa_plan()
    wet = next(d for d in it.days if any(p.category not in INDOOR for p in d.stops))
    out, _, _ = revise(it, ReviseRequest(intent="rain", day=wet.date))
    assert all(p.category in INDOOR for p in next(d for d in out.days if d.date == wet.date).stops)
    for d_old, d_new in zip(it.days, out.days):
        if d_old.date != wet.date:
            assert ids(it, d_old.date) == ids(out, d_new.date)


def test_unknown_day_or_stop_is_a_revise_error():
    with pytest.raises(ReviseError):
        revise(goa_plan(), ReviseRequest(intent="lighter_day", day=date(2027, 1, 1)))
    with pytest.raises(ReviseError):
        revise(goa_plan(), ReviseRequest(intent="swap_stop", place_id="nowhere"))


def frames(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def plan_goa():
    done = frames(client.post("/plan", json=GOA.request.model_dump(mode="json")))[-1]
    assert done["stage"] == "done"
    return done


def test_revise_endpoint_streams_and_keeps_the_old_plan():
    done = plan_goa()
    r = client.post(f"/plan/{done['plan_id']}/revise", json={"intent": "rain"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = frames(r)
    assert [e["stage"] for e in events] == ["intake", "solving", "checking", "done"]
    assert events[-1]["plan_id"] != done["plan_id"] and events[-1]["share_token"]
    revised = Itinerary.model_validate(events[-1]["partial"])
    assert all(p.category in INDOOR for d in revised.days for p in d.stops)
    # The original plan is still there and can be revised again.
    assert client.post(f"/plan/{done['plan_id']}/revise", json={"intent": "rain"}).status_code == 200


def test_revise_endpoint_errors():
    done = plan_goa()
    assert client.post("/plan/nope/revise", json={"intent": "rain"}).status_code == 404
    assert client.post(f"/plan/{done['plan_id']}/revise", json={"intent": "swap_stop", "place_id": "x"}).status_code == 422
    assert client.post(f"/plan/{done['plan_id']}/revise", json={"intent": "lighter_day"}).status_code == 422


def test_share_link_opens_a_read_only_trip():
    done = plan_goa()
    r = client.get(f"/trips/{done['share_token']}")
    assert r.status_code == 200
    assert Itinerary.model_validate(r.json()) == Itinerary.model_validate(done["partial"])
    assert client.get("/trips/not-a-token").status_code == 404
    assert client.put(f"/trips/{done['share_token']}", json={}).status_code == 405
