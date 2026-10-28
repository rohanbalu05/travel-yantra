import datetime as dt

import pytest

from routes.compare import CompareService, resolve_city
from routes.fares import cab_fare, cars, drive_cost, rail_class, rail_fare, toll
from routes.graph import HaversineRoadProvider
from routes.scripts.build_rail import classes
from ty_contracts import CompareRequest, Mode


def test_rail_fare_tapers_with_distance_and_rises_with_class():
    assert rail_fare(650, "SL") == pytest.approx(380, rel=0.1)
    assert rail_fare(2180, "SL") == pytest.approx(800, rel=0.1)
    assert rail_fare(50, "SL") == rail_fare(200, "SL")  # sleeper minimum distance
    assert rail_fare(500, "2S") < rail_fare(500, "SL") < rail_fare(500, "3A") < rail_fare(500, "2A") < rail_fare(500, "1A")


@pytest.mark.parametrize("carried,style,want", [
    (["CC", "EC"], None, "CC"), (["CC", "EC"], "luxury", "EC"), (["CC", "EC"], "budget", "CC"),
    (["2A", "3A", "SL"], None, "3A"), (["2A", "3A", "SL"], "budget", "SL"), (["2A", "3A", "SL"], "luxury", "2A"),
    (["2S"], "luxury", "2S"),
])
def test_rail_class_follows_budget_style_within_what_the_train_carries(carried, style, want):
    assert rail_class(carried, style) == want


def test_datameet_class_flags():
    shatabdi = {"type": "Shtb", "chair_car": 1, "first_ac": 1, "sleeper": 0, "third_ac": 0, "second_ac": 0}
    express = {"type": "Exp", "chair_car": 0, "first_ac": 0, "sleeper": 1, "third_ac": 1, "second_ac": 1}
    passenger = {"type": "Pass", "chair_car": 0, "first_ac": 0, "sleeper": 0, "third_ac": 0, "second_ac": 0}
    assert classes(shatabdi) == ["CC", "EC"] and classes(express) == ["2A", "3A", "SL"] and classes(passenger) == ["2S"]
    assert classes({"type": None}) == []  # the hand-made sample lists no flags


def test_cars_cabs_and_tolls_per_four():
    assert [cars(n) for n in (1, 4, 5, 8, 9)] == [1, 1, 2, 2, 3]
    assert toll("bengaluru", "mysuru") == toll("mysuru", "bengaluru") > 0 and toll("bengaluru", "panaji") == 0
    assert drive_cost(100, 300, people=5) == 2 * drive_cost(100, 300, people=4) == 2 * (700 + 300)
    assert cab_fare(0.5) == 100 and cab_fare(10, people=6) == 2 * cab_fare(10)


@pytest.fixture(scope="module")
def india():
    """The real datameet subset (box plus every city in data/cities.json), haversine roads, fake air."""
    return CompareService(road=HaversineRoadProvider(), live=False)


@pytest.mark.parametrize("origin,dest,modes", [
    ("Chennai", "Delhi", {"rail", "air"}),  # 2,000 km: too far to drive
    ("Delhi", "Agra", {"rail", "road"}),  # too close to fly
    ("Agra", "Jaipur", {"rail", "road", "air"}),  # Agra (AGR) to Jaipur is 220 km
    ("Jaipur", "Delhi", {"rail", "road", "air"}),
    ("Mumbai", "Goa", {"rail", "road", "air"}),
    ("Hyderabad", "Hampi", {"rail", "road", "air"}),
    ("Bengaluru", "Kochi", {"rail", "road", "air"}),
    ("Bengaluru", "Trivandrum", {"rail", "road", "air"}),
    ("Kochi", "Munnar", {"road"}),  # no station or airport near Munnar
    ("Munnar", "Alleppey", {"road"}),
])
def test_transport_into_the_four_regions(india, origin, dest, modes):
    r = india.compare(CompareRequest(origin=origin, destination=dest, date=dt.date(2026, 12, 11), travellers=2))
    assert {o.option.mode.value for o in r.options} == modes
    for o in r.options:
        assert o.option.total_cost_inr == sum(leg.cost_inr for leg in o.option.legs)
        assert all(leg.minutes >= 1 or leg.cost_inr == 0 for leg in o.option.legs)  # no "Rs 1, under a minute"


def test_airports_for_the_regions():
    svc = CompareService(road=HaversineRoadProvider(), live=False)
    g = svc._graph_for([resolve_city(c) for c in ("Goa", "Kochi", "Trivandrum", "Delhi", "Jaipur")])
    near = {c: {a.id[3:] for a in svc._near_airports(g, resolve_city(c))}
            for c in ("Goa", "Kochi", "Trivandrum", "Delhi", "Jaipur")}
    assert near["Goa"] >= {"GOI", "GOX"} and "COK" in near["Kochi"] and "TRV" in near["Trivandrum"]
    assert "DEL" in near["Delhi"] and "JAI" in near["Jaipur"]


def test_one_fare_model_rail_legs_by_style_and_drives_by_car(india):
    req = CompareRequest(origin="Bengaluru", destination="Mysuru", date=dt.date(2026, 12, 11), travellers=5)
    mid, lux = india.compare(req), india.compare(req, rail_class="luxury")
    rail = lambda r: next(o.option for o in r.options if o.option.mode is Mode.rail)  # noqa: E731
    road = next(o.option for o in mid.options if o.option.mode is Mode.road)
    assert sum(leg.cost_inr for leg in rail(lux).legs if leg.mode is Mode.rail) > \
        sum(leg.cost_inr for leg in rail(mid).legs if leg.mode is Mode.rail)
    km = road.legs[0].cost_inr / 2  # two cars of fuel and the expressway toll
    assert road.legs[0].cost_inr % 2 == 0 and km > 2 * toll("bengaluru", "mysuru")
    assert any("fuel" in n and "toll" in n for n in mid.notes)


def test_no_drive_longer_than_fifteen_hours():
    from routes.compare import MAX_DRIVE_MIN
    from routes.graph import Edge

    class LongRoad(HaversineRoadProvider):
        """Like the Routes API: no distance limit."""

        def road_edge(self, a, b):
            e = HaversineRoadProvider(max_km=5000).road_edge(a, b)
            return e if e is None else Edge(e.src, e.dst, e.mode, e.minutes, e.cost_inr, e.comfort, e.ref, e.km)

    r = CompareService(road=LongRoad(), live=False).compare(
        CompareRequest(origin="Chennai", destination="Delhi", date=dt.date(2026, 12, 11)))
    assert "road" not in {o.option.mode.value for o in r.options}
    assert any(u.mode.value == "road" and "15 hours" in u.reason for u in r.unavailable) and MAX_DRIVE_MIN == 900
