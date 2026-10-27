import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import router
from routes.compare import (
    CompareRequest,
    CompareService,
    Found,
    UnknownPlace,
    get_service,
    rank,
    resolve_city,
)
from routes.graph import FakeAirProvider, HaversineRoadProvider
from ty_contracts import Mode, TransportOption


@pytest.fixture(scope="module")
def service():
    return CompareService(road=HaversineRoadProvider(), air=FakeAirProvider())


@pytest.fixture(scope="module")
def client(service):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_service] = lambda: service
    return TestClient(app)


def _by_mode(resp):
    return {o.option.mode: o for o in resp.options}


def test_bengaluru_to_goa_returns_rail_road_and_air_ranked(service):
    r = service.compare(CompareRequest(origin="Bengaluru", destination="Goa", date="2026-12-11"))
    modes = _by_mode(r)
    assert set(modes) == {Mode.rail, Mode.road, Mode.air}
    assert [o.rank for o in r.options] == [1, 2, 3]
    assert r.destination.name == "Panaji" and str(r.date) == "2026-12-11"
    rail, road, air = modes[Mode.rail], modes[Mode.road], modes[Mode.air]
    assert air.option.total_minutes < rail.option.total_minutes
    assert air.option.total_minutes < road.option.total_minutes
    assert rail.option.total_cost_inr < road.option.total_cost_inr < air.option.total_cost_inr
    assert road.changes == 0 and road.sources == ["haversine"]
    assert "datameet_rail" in rail.sources and "fake_air" in air.sources
    # one rail leg per train, not one per stop pair: the 15:15 Yesvantpur-Vasco
    trains = [leg for leg in rail.option.legs if leg.mode is Mode.rail]
    assert [(t.from_, t.depart.strftime("%H:%M")) for t in trains] == [("Yesvantpur JN", "15:15")]
    assert any("airport (BLR)" in leg.from_ for leg in air.option.legs)


def test_bengaluru_to_mysuru_has_rail_and_road_and_explains_no_air(service):
    r = service.compare(CompareRequest(origin="Bangalore", destination="Mysore", date="2026-12-11"))
    modes = _by_mode(r)
    assert set(modes) == {Mode.rail, Mode.road}
    assert [u.mode for u in r.unavailable] == [Mode.air]
    assert "airport" in r.unavailable[0].reason
    rail = modes[Mode.rail]
    assert rail.option.legs[0].from_ == "Bengaluru" and rail.option.legs[-1].to == "Mysuru"
    assert any(leg.mode is Mode.rail for leg in rail.option.legs)


def test_legs_chain_from_the_requested_departure(service):
    r = service.compare(CompareRequest(origin="Bengaluru", destination="Mysuru",
                                       date="2026-12-11", depart_time="06:30"))
    for o in r.options:
        legs = o.option.legs
        if o.option.mode is Mode.rail:  # real timetable: leave in time for the train, wait between trains
            assert legs[0].depart >= dt.datetime(2026, 12, 11, 6, 30)
            assert all(a.arrive <= b.depart for a, b in zip(legs, legs[1:]))
            assert o.option.total_minutes == round((legs[-1].arrive - legs[0].depart).total_seconds() / 60)
            continue
        assert legs[0].depart.isoformat() == "2026-12-11T06:30:00"
        assert all(a.arrive == b.depart for a, b in zip(legs, legs[1:]))
        assert o.option.total_minutes == sum(leg.minutes for leg in legs)


@pytest.mark.parametrize("rank_by,key", [
    ("time", lambda o: o.option.total_minutes),
    ("cost", lambda o: o.option.total_cost_inr),
    ("changes", lambda o: o.changes),
])
def test_rank_by_orders_options(service, rank_by, key):
    r = service.compare(CompareRequest(origin="Bengaluru", destination="Goa", rank_by=rank_by))
    values = [key(o) for o in r.options]
    assert values == sorted(values)


def test_modes_filter(service):
    r = service.compare(CompareRequest(origin="Bengaluru", destination="Goa", modes=["rail"]))
    assert [o.option.mode for o in r.options] == [Mode.rail] and r.unavailable == []


def test_balanced_rank_breaks_ties_by_mode_order():
    leg = {"from": "a", "to": "b", "mode": "road", "depart": "2026-12-11T08:00:00",
           "arrive": "2026-12-11T09:00:00", "minutes": 60, "cost_inr": 100}
    opt = TransportOption(mode="road", legs=[leg], total_minutes=60, total_cost_inr=100, comfort=3)
    found = [Found(Mode.air, opt, 0, []), Found(Mode.rail, opt, 0, [])]
    assert [o.option is opt for o in rank(found, "balanced")] == [True, True]
    assert rank([], "balanced") == []


def test_resolve_city_aliases_and_unknown():
    assert resolve_city("  goa ").id == resolve_city("Panjim").id == "PL:panaji"
    with pytest.raises(UnknownPlace):
        resolve_city("Atlantis")


def test_http_compare_returns_contract_shape(client):
    res = client.post("/routes/compare", json={"origin": "Bengaluru", "destination": "Goa",
                                               "date": "2026-12-11"})
    assert res.status_code == 200
    body = res.json()
    assert body["rank_by"] == "balanced" and len(body["options"]) == 3
    first = body["options"][0]
    TransportOption.model_validate(first["option"])
    assert "from" in first["option"]["legs"][0]


@pytest.mark.parametrize("payload", [
    {"origin": "Atlantis", "destination": "Goa"},
    {"origin": "Goa", "destination": "Panaji"},
    {"origin": "Bengaluru", "destination": "Goa", "rank_by": "fastest"},
    {"origin": "Bengaluru", "destination": "Goa", "modes": []},
    {"origin": "Bengaluru", "destination": "Goa", "travellers": 0},
])
def test_http_compare_rejects_bad_input(client, payload):
    assert client.post("/routes/compare", json=payload).status_code == 422


def test_option_ids_are_stable_and_distinct(service):
    req = CompareRequest(origin="Bengaluru", destination="Goa", date="2026-12-11")
    ids = [o.id for o in service.compare(req).options]
    assert ids == [o.id for o in service.compare(req).options]
    assert len(set(ids)) == 3 and all(i.split("-")[0] in {"rail", "road", "air"} for i in ids)


def test_travellers_scale_tickets_per_person_and_cars_per_four(service):
    def costs(n):
        r = service.compare(CompareRequest(origin="Bengaluru", destination="Goa", date="2026-12-11",
                                           travellers=n))
        return {o.option.mode: o.option for o in r.options}

    one, four, five = costs(1), costs(4), costs(5)
    assert four[Mode.road].total_cost_inr == one[Mode.road].total_cost_inr
    assert five[Mode.road].total_cost_inr == 2 * one[Mode.road].total_cost_inr
    rail_legs = lambda opt: [leg.cost_inr for leg in opt.legs if leg.mode == Mode.rail]  # noqa: E731
    assert rail_legs(four[Mode.rail]) == [pytest.approx(4 * c, abs=2) for c in rail_legs(one[Mode.rail])]
    assert four[Mode.air].total_cost_inr > 3 * one[Mode.air].total_cost_inr
    assert all(o.option.total_cost_inr == sum(leg.cost_inr for leg in o.option.legs)
               for o in service.compare(CompareRequest(origin="Bengaluru", destination="Goa", travellers=4)).options)


@pytest.mark.parametrize("dest,modes,missing", [
    ("Hampi", {"rail", "road", "air"}, set()),
    ("Coorg", {"rail", "road"}, {"air"}),  # rail via Subrahmanya Road, ranked below road
    ("Madikeri", {"rail", "road"}, {"air"}),
    ("Chikmagalur", {"rail", "road"}, {"air"}),
])
def test_karnataka_destinations_for_planner(dest, modes, missing):
    svc = CompareService(road=HaversineRoadProvider(), live=False)
    resp = svc.compare(CompareRequest(origin="Bengaluru", destination=dest, date=dt.date(2026, 12, 11)))
    assert {o.option.mode.value for o in resp.options} == modes
    assert {u.mode.value for u in resp.unavailable} == missing
    assert [o.rank for o in resp.options] == list(range(1, len(modes) + 1))


def test_rail_waits_for_the_real_train_and_leaves_in_time(service):
    r = service.compare(CompareRequest(origin="Bengaluru", destination="Goa", date="2026-12-11",
                                       depart_time="08:00", modes=["rail"]))
    legs = r.options[0].option.legs
    first_train = next(leg for leg in legs if leg.mode is Mode.rail)
    # leave the centre in time for the train, plus BOARD_MIN at the station; no morning spent waiting
    assert legs[0].arrive + dt.timedelta(minutes=15) == first_train.depart
    assert first_train.depart > dt.datetime(2026, 12, 11, 8, 0)


def test_no_early_detour_onto_the_same_train(service):
    r = service.compare(CompareRequest(origin="Bengaluru", destination="Mysuru", date="2026-12-11",
                                       depart_time="08:00", modes=["rail"]))
    trains = [leg for leg in r.options[0].option.legs if leg.mode is Mode.rail]
    assert len(trains) == 1  # a direct train, not a hop out and back to catch it


def test_rail_departures_list_real_trains_in_a_window(service):
    deps = service.rail_departures("Bengaluru", "Mysuru", dt.date(2026, 12, 11), dt.time(5, 0), dt.time(10, 0))
    leaves = [o.legs[0].depart for o in deps]
    assert len(deps) >= 3 and leaves == sorted(leaves)
    assert all(dt.datetime(2026, 12, 11, 5, 0) <= t <= dt.datetime(2026, 12, 11, 10, 0) for t in leaves)
    arrivals = [o.legs[-1].arrive for o in deps]
    assert len(set(arrivals)) == len(arrivals)
    assert all(o.mode is Mode.rail and o.legs[-1].to == "Mysuru" for o in deps)


def test_sample_rail_is_the_fallback(monkeypatch):
    monkeypatch.setenv("ROUTES_RAIL", "sample")
    svc = CompareService(road=HaversineRoadProvider(), live=False)
    r = svc.compare(CompareRequest(origin="Bengaluru", destination="Goa", date="2026-12-11", modes=["rail"]))
    assert "sample_rail" in r.options[0].sources and "fictional sample" in r.notes[0]


def _opt(mode, depart, minutes, cost):
    start = dt.datetime.fromisoformat(depart)
    leg = {"from": "a", "to": "b", "mode": mode, "depart": start.isoformat(),
           "arrive": (start + dt.timedelta(minutes=minutes)).isoformat(), "minutes": minutes, "cost_inr": cost}
    return TransportOption(mode=mode, legs=[leg], total_minutes=minutes, total_cost_inr=cost, comfort=3)


@pytest.mark.parametrize("origin,dest,depart", [("Bengaluru", "Coorg", "08:00"), ("Coorg", "Bengaluru", "18:00")])
@pytest.mark.parametrize("travellers", [1, 4])
def test_coorg_prefers_road_over_the_overnight_train(service, origin, dest, depart, travellers):
    r = service.compare(CompareRequest(origin=origin, destination=dest, date="2026-11-24", depart_time=depart,
                                       travellers=travellers))
    assert r.options[0].option.mode is Mode.road
    assert any(o.option.mode is Mode.rail for o in r.options)  # still offered, just not first


def test_overnight_penalty_rules():
    night = Found(Mode.rail, _opt("rail", "2026-11-24T20:30", 600, 400), 0, [])
    short_day = Found(Mode.road, _opt("road", "2026-11-24T08:00", 360, 800), 0, [])
    long_day = Found(Mode.road, _opt("road", "2026-11-24T08:00", 900, 4000), 0, [])
    # short trip: the night train drops below the day option, alone or as a family
    for n in (1, 4):
        assert [o.option.mode for o in rank([night, short_day], "balanced", n)] == [Mode.road, Mode.rail]
    # long trip for a family: no penalty, the cheap night train stays first
    assert rank([night, long_day], "balanced", 4)[0].option.mode is Mode.rail
    # the only option, or all options overnight: no penalty
    assert rank([night], "balanced", 1)[0].score == pytest.approx(1 + 1)
    other_night = Found(Mode.road, _opt("road", "2026-11-24T23:00", 420, 1600), 0, [])
    assert rank([night, other_night], "balanced", 1)[0].option.mode is Mode.rail
    # other rank_by orders are left alone
    assert rank([night, short_day], "cost", 1)[0].option.mode is Mode.rail
