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


LODGING = "https://www.google.com/travel/lodging/clk?pc=x&pcurl="
ACLK = "https://www.google.com/aclk?sa=l&ai=x&gclid=y&adurl"


def test_stay_quotes_use_sellers_own_indian_pages():
    q = StayQuery("Mysuru", GOA_STAY.check_in, GOA_STAY.check_out, adults=3, hotel="Royal Tusker")
    found = [
        Found("Booking.com", 7440, LODGING + "https%3A%2F%2Fwww.booking.com%2Fhotel%2Fin%2Fx.html%3Fgroup_adults%3D2"),
        Found("Agoda", 7432, ACLK),  # an ad click and nothing else: left out
        Found("Royal Tusker", 5544, LODGING + "https%3A%2F%2Flive.ipms247.com%2Fbooking%2Fx%3Fadults%3D2"),
        Found("Trip.com", 6274, LODGING + "https%3A%2F%2Fuk.trip.com%2Fhotels%2Fx"),  # UK locale: left out
        Found("Vio.com", 5678, LODGING + "https%3A%2F%2Fdeals.vio.com%2F%3FuserCountry%3DGB"),
        Found("Bluepillow", 6914, "https://www.bluepillow.co.uk/x"),
        Found("Hotels.com", 5744, None),
    ]
    by = _by_seller(stay_offers(q, found, at=AT))
    # a registry seller keeps its own link for the party (3 adults, 2 rooms) with SerpApi's price
    assert by["Booking.com"].url.startswith("https://www.booking.com/searchresults.html?") and by["Booking.com"].price_inr == 7440
    assert parse_qs(urlsplit(by["Booking.com"].url).query)["group_adults"] == ["3"]
    assert parse_qs(urlsplit(by["Booking.com"].url).query)["no_rooms"] == ["2"]
    assert by["Royal Tusker"].url == "https://live.ipms247.com/booking/x?adults=2" and by["Royal Tusker"].kind == "deep_link"
    assert not {"Agoda", "Trip.com", "Vio.com", "Bluepillow", "Hotels.com"} & set(by)
    assert all("google.com" not in o.url for o in by.values())
    assert parse_qs(urlsplit(by["Airbnb"].url).query)["adults"] == ["3"]
