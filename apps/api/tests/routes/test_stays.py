import datetime as dt

import pytest

from routes.compare import UnknownPlace
from routes.stays import rank_stays

IN, OUT = dt.date(2026, 12, 11), dt.date(2026, 12, 14)


def test_goa_family_stays_ranked_by_rating_within_budget():
    stays = rank_stays("Goa", IN, OUT, party=4, budget_per_night_inr=12000, limit=3)
    assert all(s.sample for s in stays)  # no SerpApi key: fictional, and marked so
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
    # within Rs 8,000 for two rooms, the best-rated is River Side Suites (its details call is recorded)
    stays = rank_stays("Goa", IN, OUT, party=4, hotels=_live(serp), budget_per_night_inr=8000)
    top = stays[0]
    assert top.name == "River Side Suites at Panjim Gymkhana"
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
    assert len(live) == 5 and not any(s.name.startswith("Sample") for s in live)
    assert all({"Booking.com", "MakeMyTrip"} <= {o.seller for o in st.offers} for st in live)
    sample = rank_stays(city, IN, OUT, party=4, live=False, limit=3)
    assert len(sample) == 3 and all(s.name.startswith("Sample") and s.offers for s in sample)


def test_live_failure_gives_labelled_estimates_never_invented_hotels():
    from routes.apicache import MemoryStore
    from routes.hotels import SerpApiHotels
    from routes.serpapi import SerpApi

    def down(url, timeout):
        raise TimeoutError

    hotels = SerpApiHotels(SerpApi(store=MemoryStore(), transport=down, api_key="k"))
    stays = rank_stays("Goa", IN, OUT, party=4, hotels=hotels, budget_style="luxury")
    assert [s.stars for s in stays] == [5, 2, 3] and all(s.sample and s.name.startswith("Estimate: ") for s in stays)
    assert stays[0].price_per_night_inr == 2 * 16800 and stays[0].id == "panaji:estimate-luxury"
    assert all(s.rating is None and s.reviews is None and s.offers for s in stays)
    assert all("Estimate" not in (o.url or "") for s in stays for o in s.offers)  # links search the city


def test_sample_stays_link_the_city_not_the_made_up_name():
    stay = rank_stays("Goa", IN, OUT, party=4, live=False)[0]
    booking = next(o for o in stay.offers if o.seller == "Booking.com")
    assert "ss=Panaji&" in booking.url and "Sample" not in booking.url


def test_live_stays_carry_stars_rating_reviews_and_a_stable_id(serp):
    stays = rank_stays("Goa", IN, OUT, party=2, hotels=_live(serp))
    assert 3 <= len(stays) <= 5 and not any(s.sample for s in stays)
    assert all(s.rating and s.reviews and s.reviews >= 10 for s in stays)
    assert any(s.stars for s in stays) and all(s.kind in ("hotel", "rental") for s in stays)
    assert all(s.id and s.id.startswith("panaji:") for s in stays)
    assert len({s.id for s in stays}) == len(stays)
    again = rank_stays("Goa", IN, OUT, party=2, hotels=_live(serp))
    assert [s.id for s in again] == [s.id for s in stays]


def test_no_three_bedroom_rental_for_two(serp):
    """Coorg's search has 2- and 3-bedroom villas: two people get at most a 2-bedroom; six get neither."""
    from routes.hotels import bedrooms

    two = rank_stays("Coorg", IN, OUT, party=2, hotels=_live(serp), limit=20)
    assert all((bedrooms(s.name) or 0) <= 2 for s in two)
    assert any(s.name.startswith("WildWood") for s in rank_stays("Coorg", IN, OUT, party=5, hotels=_live(serp),
                                                                 limit=20))


@pytest.mark.parametrize("style", ["budget", "mid", "luxury"])
def test_budget_style_orders_stays(serp, style):
    stays = rank_stays("Goa", IN, OUT, party=2, hotels=_live(serp), budget_style=style)
    prices = [s.price_per_night_inr for s in stays]
    if style == "budget":
        assert prices[0] == min(prices) and stays[0].rating >= 3.8
    if style == "luxury":
        assert stays[0].stars == 5 and prices[0] > 10000
    if style == "mid":
        assert stays[0].stars in (3, 4, None) and stays[0].rating >= 4.3


def test_ratings_with_few_reviews_count_less():
    from routes.stays import score

    assert score({"rating": 5.0, "reviews": 3}) < score({"rating": 4.6, "reviews": 2000})
    assert score({"rating": None, "reviews": None}) == 0


def test_no_style_ranks_as_comfort_not_the_top_rated_palace(serp):
    """Seniors with no style said got Taj Palace at Rs 38,000 a night: no style is mid (3-4 star)."""
    plain = rank_stays("Goa", IN, OUT, party=2, hotels=_live(serp))
    mid = rank_stays("Goa", IN, OUT, party=2, hotels=_live(serp), budget_style="comfort")
    assert [s.name for s in plain] == [s.name for s in mid] and plain[0].stars in (3, 4, None)
