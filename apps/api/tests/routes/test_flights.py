import datetime as dt
import json
from pathlib import Path

from routes.compare import AIRPORT_MIN, CompareService
from routes.flights import SerpApiFlights, parse_booking, parse_flights
from routes.graph import HaversineRoadProvider
from ty_contracts import CompareRequest, Mode

SERP = Path(__file__).resolve().parent / "fixtures" / "serpapi"
DAY = dt.date(2026, 12, 11)


def _load(name):
    return json.loads((SERP / f"{name}.json").read_text(encoding="utf-8"))


def _service(serp):
    api, _ = serp
    return CompareService(road=HaversineRoadProvider(), flights=SerpApiFlights(api))


def _air(resp):
    return next(o for o in resp.options if o.option.mode is Mode.air)


def test_parse_recorded_flights_and_booking_options():
    flights = parse_flights(_load("flights_blr_goi"), "BLR", "GOI")
    assert len(flights) >= 10 and all(f.price_inr > 0 and f.arrive > f.depart for f in flights)
    one_stop = [f for f in flights if f.stops]
    assert one_stop and all(" + " in f.number for f in one_stop)
    sellers = parse_booking(_load("flights_blr_vdy_booking"))
    assert len({s.seller for s in sellers}) >= 3 and all(s.price_inr > 0 and s.url is None for s in sellers)


def test_hampi_air_uses_the_live_flight_and_shows_several_sellers(serp):
    resp = _service(serp).compare(CompareRequest(origin="Bengaluru", destination="Hampi", date=DAY,
                                                 depart_time=dt.time(8, 0), travellers=4))
    air = _air(resp)
    assert "serpapi_flights" in air.sources
    flight = next(leg for leg in air.option.legs if leg.mode is Mode.air)
    # S5 701 leaves 10:25 and flies 50 min; the leg starts AIRPORT_MIN earlier
    assert flight.depart == dt.datetime(2026, 12, 11, 10, 25) - dt.timedelta(minutes=AIRPORT_MIN)
    assert flight.minutes == AIRPORT_MIN + 50 and flight.cost_inr == 4 * 4755
    assert air.option.legs[0].depart >= dt.datetime(2026, 12, 11, 8, 0)
    priced = [o for o in air.option.offers if o.price_inr is not None]
    assert len({o.seller for o in priced}) >= 3
    assert priced == sorted(priced, key=lambda o: o.price_inr)
    assert {o.seller for o in air.option.offers} >= {"MakeMyTrip", "Cleartrip", "ixigo", "Goibibo", "Star Air"}
    assert "Google Flights" in " ".join(resp.notes)


def test_goa_air_picks_the_reachable_flight_best_on_arrival_and_fare(serp):
    api, t = serp
    resp = _service(serp).compare(CompareRequest(origin="Bengaluru", destination="Goa", date=DAY, travellers=4))
    air = _air(resp)
    flight = next(leg for leg in air.option.legs if leg.mode is Mode.air)
    # flights before ~09:50 cannot be reached from an 08:00 start. Of the rest, 6E 6653 (12:25,
    # Rs 8,353) beats 6E 6583 (11:20, Rs 10,243): 65 min later for Rs 1,890 less, at Rs 10 a minute
    assert flight.depart == dt.datetime(2026, 12, 11, 12, 25) - dt.timedelta(minutes=AIRPORT_MIN)
    assert flight.cost_inr == 4 * 8353
    by = {o.seller: o for o in air.option.offers}
    assert by["IndiGo"].price_inr == 4 * 8353 and air.option.offers[0].seller == "IndiGo"
    assert {"MakeMyTrip", "Goibibo", "Cleartrip", "ixigo"} <= set(by)
    # one search per airport pair (BLR-GOI, BLR-GOX) and one booking; a second compare is all cache
    searches = [c for c in t.calls if "booking_token" not in c]
    assert sorted(c["arrival_id"] for c in searches) == ["GOI", "GOX"] and len(t.calls) == 3
    n = len(t.calls)
    _service(serp).compare(CompareRequest(origin="Bengaluru", destination="Goa", date=DAY, travellers=4))
    assert len(t.calls) == n


def test_no_live_answer_keeps_the_estimate():
    svc = CompareService(road=HaversineRoadProvider(), live=False)
    resp = svc.compare(CompareRequest(origin="Bengaluru", destination="Goa", date=DAY))
    air = _air(resp)
    assert air.sources.count("fake_air") == 1 and air.option.offers  # estimate, with seller links
    assert "estimated" in " ".join(resp.notes)


def test_no_reachable_flight_makes_air_unavailable(serp):
    resp = _service(serp).compare(CompareRequest(origin="Bengaluru", destination="Hampi", date=DAY,
                                                 depart_time=dt.time(12, 0)))
    assert Mode.air not in {o.option.mode for o in resp.options}
    assert any(u.mode is Mode.air for u in resp.unavailable)
