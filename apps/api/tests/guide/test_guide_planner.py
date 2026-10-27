from datetime import date, time

from guide.planner import SOURCE, _pois, corpus_city, places_for, places_for_request
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
    # Hours from Places where it confirmed them; unknown (empty), never invented, where not.
    assert len(basilica.opening_hours) == 7 and basilica.opening_hours[0].day == "mon"
    divar = next(p for p in goa if p.name == "Divar Island")
    assert divar.opening_hours == []
