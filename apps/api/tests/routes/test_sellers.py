import datetime as dt
from urllib.parse import parse_qs, urlsplit

from routes.sellers import FlightQuery, Found, StayQuery, flight_offers, stay_offers

AT = dt.datetime(2026, 10, 27, 12, 0, tzinfo=dt.UTC)
GOA_STAY = StayQuery("Panaji", dt.date(2026, 12, 11), dt.date(2026, 12, 14), adults=4)
GOA_FLIGHT = FlightQuery("BLR", "GOI", dt.date(2026, 12, 11), adults=4)


def _by_seller(offers):
    return {o.seller: o for o in offers}


def test_goa_stay_links_for_every_registry_seller():
    offers = _by_seller(stay_offers(GOA_STAY, at=AT))
    assert set(offers) == {"Booking.com", "Airbnb", "MakeMyTrip", "Goibibo", "Cleartrip", "ixigo"}
    assert {s for s, o in offers.items() if o.kind == "deep_link"} == {"Booking.com", "Airbnb", "MakeMyTrip"}
    for o in offers.values():
        u = urlsplit(o.url)
        assert u.scheme == "https" and u.netloc and o.price_inr is None and o.fetched_at == AT
    q = parse_qs(urlsplit(offers["Booking.com"].url).query)
    assert q["ss"] == ["Panaji"] and q["checkin"] == ["2026-12-11"] and q["checkout"] == ["2026-12-14"]
    assert q["group_adults"] == ["4"] and q["no_rooms"] == ["2"]
    assert urlsplit(offers["Airbnb"].url).path == "/s/Panaji/homes"
    mmt = parse_qs(urlsplit(offers["MakeMyTrip"].url).query)
    assert mmt["checkin"] == ["12112026"] and mmt["roomStayQualifier"] == ["4e0e"]


def test_goa_flight_links():
    offers = _by_seller(flight_offers(GOA_FLIGHT, at=AT))
    assert set(offers) == {"MakeMyTrip", "Goibibo", "Cleartrip", "ixigo"}
    q = parse_qs(urlsplit(offers["MakeMyTrip"].url).query)
    assert q["itinerary"] == ["BLR-GOI-11/12/2026"] and q["paxType"] == ["A-4_C-0_I-0"]
    assert offers["MakeMyTrip"].kind == "deep_link" and offers["Cleartrip"].kind == "check_price"
    assert "air-BLR-GOI-20261211--4-0-0-E-D" in offers["Goibibo"].url


def test_serpapi_prices_merge_into_registry_and_unknown_sellers_get_check_price():
    found = [Found("Cleartrip", 19008), Found("Star Air", 19020), Found("cleartrip", 21000)]
    offers = flight_offers(GOA_FLIGHT, found, at=AT)
    by = _by_seller(offers)
    assert by["Cleartrip"].price_inr == 19008  # the seller's cheapest quote, registry link kept
    assert by["Cleartrip"].url.startswith("https://www.cleartrip.com/")
    assert by["Star Air"].kind == "check_price" and by["Star Air"].url.startswith("https://www.google.com/search?")
    assert [o.seller for o in offers[:2]] == ["Cleartrip", "Star Air"]  # priced first, cheapest first
    assert len(offers) == 5


def test_stay_quotes_keep_the_property_link():
    q = StayQuery("Panaji", GOA_STAY.check_in, GOA_STAY.check_out, adults=2, hotel="River Side Suites")
    found = [Found("Booking.com", 7440, "https://www.google.com/travel/lodging/x"), Found("Agoda", 7432, None)]
    by = _by_seller(stay_offers(q, found, at=AT))
    assert by["Booking.com"].url == "https://www.google.com/travel/lodging/x" and by["Booking.com"].price_inr == 7440
    assert by["Agoda"].kind == "check_price" and "River+Side+Suites" in by["Agoda"].url.replace("%20", "+")
    assert parse_qs(urlsplit(by["Airbnb"].url).query)["adults"] == ["2"]
