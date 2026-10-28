"""Name matching for Katha subjects and cities (WA-11, WA-12). No database: a fake poi table."""

import pytest

from guide.katha.facts import UnknownSubject, _poi_by_name_or_slug, resolve
from guide.names import best, normalize
from guide.planner import corpus_city

POIS = [  # (id, name, city, name_kn): sample rows shaped like the poi table
    (1, "Mysore Palace", "Mysuru", "ಮೈಸೂರು ಅರಮನೆ"),
    (2, "Chamundeshwari Temple", "Mysuru", "ಚಾಮುಂಡೇಶ್ವರಿ ದೇವಸ್ಥಾನ"),
    (3, "Vittala Temple and Stone Chariot", "Hampi", "ವಿಠ್ಠಲ ದೇವಸ್ಥಾನ"),
    (4, "Devaraja Market", "Mysuru", "ದೇವರಾಜ ಮಾರುಕಟ್ಟೆ"),
    (5, "Daria Daulat Bagh (Tipu Sultan's Summer Palace), Srirangapatna", "Mysuru", None),
    (6, "Bangalore Palace", "Bengaluru", None),
    (7, "Raja's Seat", "Coorg", None),
    (8, "Lalbagh Botanical Garden", "Bengaluru", None),
    (9, "Lalbagh Glass House", "Bengaluru", None),
]


class Pois:
    def execute(self, sql, params=()):
        class R:
            def fetchall(self):
                return POIS

        return R()


@pytest.mark.parametrize(("typed", "name"), [
    ("story mysuru palace", "Mysore Palace"),  # WA-11
    ("The Mysore Palace!", "Mysore Palace"),
    ("mysuru-mysore-palace", "Mysore Palace"),  # the planner slug
    ("Chamundi temple", "Chamundeshwari Temple"),  # Chamundi <-> Chamundeshwari
    ("Vitthala Temple", "Vittala Temple and Stone Chariot"),  # Vittala <-> Vitthala, then prefix
    ("bengaluru palace", "Bangalore Palace"),  # Bengaluru <-> Bangalore
    ("Daria Daulat Bagh (Tipu Sultan's Summer Palace), Srirangapatnam", "Daria Daulat Bagh (Tipu Sultan's Summer Palace), Srirangapatna"),
    ("story of devaraja markett", "Devaraja Market"),  # difflib, one clear winner
    ("मैसूर पैलेस की कहानी", "Mysore Palace"),  # WA-12: Hindi demo names
    ("चामुंडी मंदिर", "Chamundeshwari Temple"), ("विट्ठल मंदिर", "Vittala Temple and Stone Chariot"),
    ("देवराज मार्केट", "Devaraja Market"),
    ("ಮೈಸೂರು ಅರಮನೆ ಕಥೆ", "Mysore Palace"),  # Kannada: the demo table and name_kn
    ("ದೇವರಾಜ ಮಾರುಕಟ್ಟೆ", "Devaraja Market"),
])  # fmt: skip
def test_typed_place_names_find_their_poi(typed, name) -> None:
    hit = _poi_by_name_or_slug(Pois(), typed)
    assert hit and hit[1] == name


@pytest.mark.parametrize("typed", ["Taj Mahal", "Lalbagh", "palace", "story", ""])
def test_unknown_or_ambiguous_names_find_nothing(typed) -> None:
    # "Lalbagh" prefixes two places and "palace" matches none clearly: no guess.
    assert _poi_by_name_or_slug(Pois(), typed) is None


@pytest.mark.parametrize(("typed", "city"), [
    ("Mysore", "Mysuru"), ("the city of Mysore", "Mysuru"), ("Mysuuru", "Mysuru"),
    ("Bangalore", "Bengaluru"), ("Kodagu", "Coorg"), ("Coorg", "Coorg"),
    ("Chikkamagaluru", "Chikmagalur"), ("Srirangapatna", "Mysuru"),
    ("मैसूर", "Mysuru"), ("ಮೈಸೂರು", "Mysuru"), ("हम्पी की कहानी", "Hampi"), ("ಹಂಪಿ", "Hampi"),
    ("Kashmir", None), ("Pune", None),
])  # fmt: skip
def test_corpus_city_spellings_and_languages(typed, city) -> None:
    assert corpus_city(typed) == city


def test_resolve_place_and_city_use_the_same_matching() -> None:
    assert resolve(Pois(), "place", "story mysuru palace").name == "Mysore Palace"
    assert resolve(Pois(), "city", "मैसूर").name == "Mysuru"
    with pytest.raises(UnknownSubject):
        resolve(Pois(), "place", "Taj Mahal")


@pytest.mark.parametrize("typed", ["Hampi", "hampi", "ಹಂಪಿ", "Mysore"])
def test_a_place_request_naming_a_city_exactly_tells_the_city(typed) -> None:
    # HQ P7: "story Hampi" told Hampi Bazaar's story (a prefix match), not the city's.
    pois = [*POIS, (10, "Hampi Bazaar", "Hampi", None), (11, "Mysore Zoo", "Mysuru", None)]

    class Rows(Pois):
        def execute(self, sql, params=()):
            class R:
                def fetchall(self):
                    return pois

            return R()

    subject = resolve(Rows(), "place", typed)
    assert subject.kind == "city" and subject.name == corpus_city(typed)
    assert resolve(Rows(), "place", "Hampi Bazaar").name == "Hampi Bazaar"  # still the place
    assert resolve(Rows(), "place", "Hampi Baz").kind == "place"  # a place, not exactly a city


def test_normalize_and_best() -> None:
    assert normalize("Tell me the story of the Mysore Palace.") == "mysuru palace"
    assert best("Devaraja Markt", ["Devaraja Market", "Mysore Palace"]) == "Devaraja Market"
    assert best("Lalbagh Gardn", ["Lalbagh Garden", "Lalbagh Gardens"]) is None  # no clear winner
    assert best("zzz", ["Mysore Palace"]) is None


@pytest.mark.parametrize(("typed", "name"), [
    ("ताज महल", "Taj Mahal"), ("लाल किला", "Red Fort"), ("Qutb Minar", "Qutub Minar"),
    ("Amer Fort", "Amber Fort"), ("हवा महल", "Hawa Mahal"), ("story of fort kochi", "Fort Kochi"),
])  # fmt: skip
def test_hq_p8_katha_subjects_resolve(typed, name) -> None:
    pois = [(20, "Taj Mahal", "Agra", None), (21, "Red Fort", "Delhi", None), (22, "Qutub Minar", "Delhi", None),
            (23, "Amber Fort", "Jaipur", None), (24, "Hawa Mahal", "Jaipur", None), (25, "Fort Kochi", "Kochi", None),
            (26, "Alleppey backwaters", "Alleppey", None)]  # fmt: skip

    class Rows:
        def execute(self, sql, params=()):
            class R:
                def fetchall(self):
                    return pois

            return R()

    subject = resolve(Rows(), "place", typed)
    assert subject.kind == "place" and subject.name == name
