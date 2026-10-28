import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from core import fakes
from core.checker import budget, check
from core.revise import ReviseError, indoor, revise
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
    # From TY2's corpus when it covers the city, else from the sample alternatives.
    from guide.planner import places_for

    assert new in {p.id for p in places_for("Goa")} | {p.id for p in fakes.alternatives(GOA.request)}
    assert len(ids(out)) == len(ids(it)) and check(out) == []


def test_rain_moves_every_stop_indoors_and_passes_the_checker():
    it = goa_plan()
    assert any(not indoor(p) for d in it.days for p in d.stops)  # Miramar beach, Fontainhas walk
    out, what, _ = revise(it, ReviseRequest(intent="rain"))
    assert all(indoor(p) for d in out.days for p in d.stops)
    assert what.startswith("Rain plan:") and check(out) == []


def test_rain_on_one_day_leaves_the_other_days_alone():
    it = goa_plan()
    wet = next(d for d in it.days if any(not indoor(p) for p in d.stops))
    out, _, _ = revise(it, ReviseRequest(intent="rain", day=wet.date))
    assert all(indoor(p) for p in next(d for d in out.days if d.date == wet.date).stops)
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


def test_revise_endpoint_streams_and_keeps_one_trip():
    done = plan_goa()
    r = client.post(f"/plan/{done['plan_id']}/revise", json={"intent": "rain"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = frames(r)
    assert [e["stage"] for e in events] == ["intake", "solving", "checking", "done"]
    # P9: one trip identity across revisions; the share link follows the latest version.
    assert (events[-1]["plan_id"], events[-1]["share_token"]) == (done["plan_id"], done["share_token"])
    revised = Itinerary.model_validate(events[-1]["partial"])
    assert all(indoor(p) for d in revised.days for p in d.stops)
    assert Itinerary.model_validate(client.get(f"/trips/{done['share_token']}").json()) == revised
    saved = client.get(f"/plan/{done['plan_id']}").json()
    assert saved["version"] == 2 and Itinerary.model_validate(saved["itinerary"]) == revised
    assert client.post(f"/plan/{done['plan_id']}/revise", json={"intent": "rain"}).status_code == 200
    assert client.get(f"/plan/{done['plan_id']}").json()["version"] == 3


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


def test_swap_then_lighter_changes_the_day_through_the_endpoint():
    # QA #108: "Make Sun lighter" said Done but nothing changed (after swapping Sunday's first stop).
    body = {"origin": "Bengaluru", "destinations": ["Mysuru"], "start_date": "2026-10-31", "end_date": "2026-11-01"}
    first = frames(client.post("/plan", json=body))[-1]
    sunday = first["partial"]["days"][-1]
    swapped = frames(client.post(f"/plan/{first['plan_id']}/revise",
                                 json={"intent": "swap_stop", "place_id": sunday["stops"][0]["id"]}))[-1]
    before = [s["id"] for s in swapped["partial"]["days"][-1]["stops"]]
    lighter = frames(client.post(f"/plan/{swapped['plan_id']}/revise",
                                 json={"intent": "lighter_day", "day": sunday["date"]}))
    after = [s["id"] for s in lighter[-1]["partial"]["days"][-1]["stops"]]
    assert len(after) == len(before) - 1 and set(after) < set(before)
    assert lighter[-1]["plan_id"] == swapped["plan_id"] == first["plan_id"]
    assert lighter[1]["message"].startswith(("Moved", "Dropped"))


def test_an_intent_without_a_handler_is_a_422_never_a_silent_rain_plan():
    done = plan_goa()
    r = client.post(f"/plan/{done['plan_id']}/revise", json={"intent": "rest_of_day", "now": "2026-12-12T10:00:00"})
    assert r.status_code == 422 and "not available yet" in r.json()["detail"]
    with pytest.raises(ReviseError):
        revise(goa_plan(), ReviseRequest(intent="rest_of_day", now="2026-12-12T10:00:00"))


MYSURU_REAL = {"origin": "Bengaluru", "destinations": ["Mysuru"], "start_date": "2026-10-31", "end_date": "2026-11-01",
               "constraints": {"travellers": [{"name": "Arjun", "age": 40}, {"name": "Meera", "age": 38}]}}


def corpus_plan():
    from core import steps

    return steps.replan(steps.TripRequest.model_validate(MYSURU_REAL))


def test_lighter_never_drops_the_days_top_sight():
    # Rohan's live test: "Make Sat lighter" dropped Mysore Palace.
    from core.revise import ranks

    it = corpus_plan()
    day = max(it.days, key=lambda d: len(d.stops))
    rank = ranks(it, "Mysuru")
    top = min(day.stops, key=lambda p: rank.get(p.id, 10_000))
    out, what, _ = revise(it, ReviseRequest(intent="lighter_day", day=day.date))
    assert top.id in ids(out, day.date) and len(ids(out, day.date)) < len(day.stops)
    assert top.name not in what


def test_swap_never_picks_the_same_site():
    # Chamundeshwari Temple was swapped for Chamundi Hill (the hill it stands on).
    from core.revise import same_site

    it = corpus_plan()
    for day in it.days:
        for old in day.stops:
            out, what, _ = revise(it, ReviseRequest(intent="swap_stop", place_id=old.id))
            new = [p for p in next(d for d in out.days if d.date == day.date).stops if p.id not in ids(it)]
            assert all(not same_site(p, old) for p in new), what


def test_same_site_by_distance_or_name():
    from core.revise import same_site
    from ty_contracts import Place

    def at(name, lat, lng):
        return Place(id=name, name=name, lat=lat, lng=lng, category="x", typical_visit_minutes=30, source="test")

    temple = at("Chamundeshwari Temple", 12.2724, 76.6702)
    assert same_site(temple, at("Chamundi Hills viewpoint", 12.30, 76.70))  # a shared name, 4 km away
    assert same_site(temple, at("Nandi", 12.2760, 76.6720))  # 450 m
    assert not same_site(temple, at("Mysore Palace", 12.3052, 76.6552))


def test_rain_uses_indoor_places_never_food_and_never_the_same_place_again():
    from core.revise import indoor

    it = corpus_plan()
    out, what, _ = revise(it, ReviseRequest(intent="rain"))
    stops = [p for d in out.days for p in d.stops]
    assert stops and all(indoor(p) and p.category != "food" for p in stops)
    assert len({p.name for p in stops}) == len(stops)
    for change in what.removeprefix("Rain plan: ").split("; "):
        if " → " in change:
            a, b = change.split(" → ")
            assert a != b, what
    goa, gwhat, _ = revise(goa_plan(), ReviseRequest(intent="rain"))
    assert "Basilica of Bom Jesus → Basilica of Bom Jesus" not in gwhat
