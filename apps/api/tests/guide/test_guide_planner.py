from datetime import date, time

import pytest

from guide.planner import (
    SOURCE,
    _pois,
    corpus_city,
    place_ids,
    places_for,
    places_for_request,
)
from ty_contracts import Constraints, Traveller, TripRequest

POP = {p["name"]: p.get("popularity") or 0 for p in _pois()}


def test_every_city_has_ranked_places_with_categories_and_hours() -> None:
    for city, n in (("Mysuru", 28), ("Hampi", 28), ("Bengaluru", 23), ("Chikmagalur", 18), ("Coorg", 15)):
        places = places_for(city)
        assert len(places) == n
        assert all(p.source == SOURCE and p.category and p.typical_visit_minutes > 0 for p in places)
        assert all(p.opening_hours for p in places)
    top = places_for("Mysuru", limit=3)
    assert len(top) == 3 and all(p.id in {q.id for q in places_for("Mysuru")[:3]} for p in top)
    pops = [POP[p.name] for p in places_for("Mysuru")]
    assert pops == sorted(pops, reverse=True)


def test_ids_are_unique_stable_slugs() -> None:
    ids = [p.id for c in ("Mysuru", "Hampi", "Bengaluru", "Chikmagalur", "Coorg") for p in places_for(c)]
    assert len(ids) == len(set(ids)) == 112
    assert "mysuru-mysore-palace" in ids
    assert all(i == i.lower() and " " not in i for i in ids)


def test_closed_days_are_left_out_of_the_hours() -> None:
    (zoo,) = [p for p in places_for("Mysuru") if p.name.startswith("Mysore Zoo")]
    assert "tue" not in {h.day for h in zoo.opening_hours} and len(zoo.opening_hours) == 6
    assert zoo.opening_hours[0].opens == time(8, 30)


def test_aliases_filters_and_exclude() -> None:
    assert corpus_city("Mysore") == corpus_city(" mysuru ") == "Mysuru"
    assert places_for("Kodagu") == places_for("Coorg")
    assert places_for("Kashmir") == []
    temples = places_for("Hampi", categories={"temple"})
    assert temples and all(p.category == "temple" for p in temples)
    first = places_for("Mysuru")[0].id
    assert first not in {p.id for p in places_for("Mysuru", exclude={first})}


def test_kannada_names_come_through() -> None:
    palace = next(p for p in places_for("Mysuru") if p.id == "mysuru-mysore-palace")
    assert palace.native_names["kn"] == "ಮೈಸೂರು ಅರಮನೆ"


def test_an_elderly_party_sees_friendly_places_first_within_a_popularity() -> None:
    def unfriendly_before_friendly(places, flags):
        by_pop: dict = {}
        for p in places:
            by_pop.setdefault(flags[p.name][0], []).append(flags[p.name][1])
        return any(v != sorted(v, key=lambda f: f is False) for v in by_pop.values())

    flags = {p["name"]: (p.get("popularity"), p.get("elderly_friendly")) for p in _pois()}
    for city in ("Mysuru", "Hampi", "Bengaluru", "Chikmagalur", "Coorg"):
        assert not unfriendly_before_friendly(places_for(city, elderly=True), flags)


def test_places_for_a_request_spans_destinations_in_order() -> None:
    req = TripRequest(
        origin="Bengaluru", destinations=["Mysore", "Coorg"],
        start_date=date(2026, 12, 20), end_date=date(2026, 12, 23),
        constraints=Constraints(travellers=[Traveller(name="Arjun Rao", age=70)]),
    )  # fmt: skip
    places = places_for_request(req)
    assert len(places) == 28 + 15
    assert places[0].id.startswith("mysuru-") and places[-1].id.startswith("coorg-")


def test_goa_corridor_has_at_least_ten_places_with_native_names() -> None:
    goa = places_for("Panjim")
    assert len(goa) >= 10 and goa == places_for("Goa")
    named = [p for p in goa if p.native_names]
    assert len(named) >= 10
    basilica = next(p for p in goa if p.name == "Basilica of Bom Jesus")
    assert basilica.native_names["kn"] and basilica.id == "goa-basilica-of-bom-jesus"
    # Offline the corpus has no Goa hours (Places terms: the repo keeps place ids only);
    # unknown, never invented. guide.hours fills them at runtime.
    assert basilica.opening_hours == []
    assert "goa-basilica-of-bom-jesus" in place_ids() and "goa-divar-island" not in place_ids()


def test_covered_cities_and_indoor_places_for_rain_plans() -> None:
    from guide.planner import covered_cities, indoor_ids

    cities = covered_cities()
    assert cities["Mysuru"] == "Karnataka" and cities["Goa"] == "Goa"
    indoor = indoor_ids()
    for name in ("mysuru-mysore-palace", "goa-basilica-of-bom-jesus", "bengaluru-hal-aerospace-museum",
                 "goa-mangueshi-temple"):  # fmt: skip
        assert name in indoor, name
    for name in ("hampi-vittala-temple-and-stone-chariot", "hampi-lotus-mahal-zenana-enclosure",
                 "goa-fort-aguada", "bengaluru-bangalore-fort", "mysuru-devaraja-market"):  # fmt: skip
        assert name not in indoor, name


@pytest.mark.parametrize(("typed", "city"), [
    ("Cochin", "Kochi"), ("Fort Kochi", "Kochi"), ("Alappuzha", "Alleppey"), ("New Delhi", "Delhi"),
    ("आगरा", "Agra"), ("जयपुर", "Jaipur"), ("Munnar", "Munnar"),
])  # fmt: skip
def test_kerala_and_golden_triangle_cities(typed, city) -> None:
    from guide.planner import corpus_city, covered_cities

    assert corpus_city(typed) == city
    assert covered_cities()[city] in {"Kerala", "Golden Triangle"}


def test_new_regions_have_places_ticket_links_and_indoor_flags() -> None:
    from guide.planner import indoor_ids

    taj = next(p for p in places_for("Agra") if p.name == "Taj Mahal")
    assert taj.ticket_url == "https://www.tajmahal.gov.in/" and taj.native_names["hi"] == "ताजमहल"
    amber = next(p for p in places_for("Jaipur") if p.name == "Amber Fort")
    assert amber.ticket_url and amber.ticket_url.startswith("https://obms-tourist.rajasthan.gov.in")
    assert all(p.ticket_url is None for p in places_for("Munnar"))  # no official ticket site known
    assert "delhi-national-museum" in indoor_ids() and "delhi-india-gate" not in indoor_ids()
    for city in ("Kochi", "Munnar", "Alleppey", "Delhi", "Agra", "Jaipur"):
        assert len(places_for(city)) >= 14, city
