import datetime as dt

import pytest

from routes.compare import UnknownPlace
from routes.stays import rank_stays

IN, OUT = dt.date(2026, 12, 11), dt.date(2026, 12, 14)


def test_goa_family_stays_ranked_by_rating_within_budget():
    stays = rank_stays("Goa", IN, OUT, party=4, budget_per_night_inr=12000)
    assert [s.name for s in stays] == ["Sample Fontainhas Heritage Stay", "Sample Mandovi Riverside Inn",
                                       "Sample Altinho Budget Rooms"]
    assert all(s.city == "Panaji" and s.check_in == IN and s.check_out == OUT for s in stays)
    # 4 people in rooms that sleep 3: two rooms
    assert stays[0].price_per_night_inr == 2 * 5600


def test_over_budget_stays_come_last_cheapest_first():
    stays = rank_stays("Panaji", IN, OUT, party=2, budget_per_night_inr=2000, limit=4)
    assert stays[0].name == "Sample Altinho Budget Rooms"
    assert [s.price_per_night_inr for s in stays[1:]] == [4200, 5600, 7800]


def test_no_budget_ranks_by_rating_and_limit():
    stays = rank_stays("Mysore", IN, OUT, party=2, limit=2)
    assert [s.name for s in stays] == ["Sample Chamundi Hills Retreat", "Sample Palace View Residency"]


@pytest.mark.parametrize("args,exc", [
    (("Atlantis", IN, OUT), UnknownPlace),
    (("Chennai", IN, OUT), UnknownPlace),
    (("Goa", OUT, IN), ValueError),
    (("Goa", IN, IN), ValueError),
])
def test_bad_input(args, exc):
    with pytest.raises(exc):
        rank_stays(*args)


def test_bad_party():
    with pytest.raises(ValueError):
        rank_stays("Goa", IN, OUT, party=0)


def _live(serp):
    from routes.hotels import SerpApiHotels

    return SerpApiHotels(serp[0])


def test_live_goa_top_stay_has_prices_from_two_sources(serp):
    stays = rank_stays("Goa", IN, OUT, party=4, hotels=_live(serp))
    top = stays[0]
    priced = [o for o in top.offers if o.price_inr is not None]
    assert len({o.seller for o in priced}) >= 2
    # four people need two rooms: prices are for the party per night
    assert top.price_per_night_inr % 2 == 0 and all(o.price_inr % 2 == 0 for o in priced)
    assert {"Booking.com", "Airbnb", "MakeMyTrip", "Goibibo", "Cleartrip", "ixigo"} <= {o.seller for o in top.offers}
    assert not top.name.startswith("Sample")
    # one search and one details call (the top stay only)
    assert len(serp[1].calls) == 2 and "property_token" in serp[1].calls[1]


@pytest.mark.parametrize("city", ["Coorg", "Hampi", "Chikmagalur"])
def test_new_cities_live_and_sample(serp, city):
    live = rank_stays(city, IN, OUT, party=4, hotels=_live(serp))
    assert len(live) == 3 and not any(s.name.startswith("Sample") for s in live)
    assert any(o.price_inr is not None for o in live[0].offers)
    sample = rank_stays(city, IN, OUT, party=4, live=False)
    assert len(sample) == 3 and all(s.name.startswith("Sample") and s.offers for s in sample)


def test_live_failure_falls_back_to_samples():
    from routes.apicache import MemoryStore
    from routes.hotels import SerpApiHotels
    from routes.serpapi import SerpApi

    def down(url, timeout):
        raise TimeoutError

    hotels = SerpApiHotels(SerpApi(store=MemoryStore(), transport=down, api_key="k"))
    stays = rank_stays("Goa", IN, OUT, party=4, hotels=hotels)
    assert stays[0].name.startswith("Sample")


def test_sample_stays_link_the_city_not_the_made_up_name():
    stay = rank_stays("Goa", IN, OUT, party=4, live=False)[0]
    booking = next(o for o in stay.offers if o.seller == "Booking.com")
    assert "ss=Panaji&" in booking.url and "Sample" not in booking.url
