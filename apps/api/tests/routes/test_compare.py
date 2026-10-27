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
    assert "sample_rail" in rail.sources and "fake_air" in air.sources
    # one rail leg per train, not one per stop pair
    assert [leg.mode for leg in rail.option.legs].count(Mode.rail) == 1
    assert any("airport (BLR)" in leg.from_ for leg in air.option.legs)


def test_bengaluru_to_mysuru_has_rail_and_road_and_explains_no_air(service):
    r = service.compare(CompareRequest(origin="Bangalore", destination="Mysore", date="2026-12-11"))
    modes = _by_mode(r)
    assert set(modes) == {Mode.rail, Mode.road}
    assert [u.mode for u in r.unavailable] == [Mode.air]
    assert "airport" in r.unavailable[0].reason
    rail = modes[Mode.rail]
    assert any(leg.to == "Mysuru Jn" for leg in rail.option.legs)


def test_legs_chain_from_the_requested_departure(service):
    r = service.compare(CompareRequest(origin="Bengaluru", destination="Mysuru",
                                       date="2026-12-11", depart_time="06:30"))
    for o in r.options:
        legs = o.option.legs
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
