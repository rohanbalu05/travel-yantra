from datetime import date

from guide.season import MONTHS, months_in, notes_for, notes_from

OCT_JAN = (10, 11, 12, 1)


def test_month_ranges_and_single_months() -> None:
    assert months_in("the monsoon (June to October)") == ["jun", "jul", "aug", "sep", "oct"]
    assert months_in("mid-November to mid-February") == ["jan", "feb", "nov", "dec"]
    assert months_in("Winter – November to January") == ["jan", "nov", "dec"]
    assert months_in("every year during the first week of November") == ["nov"]
    assert months_in("You may see rain any time") == []  # "may" the verb
    assert months_in("heaviest from May to July") == ["may", "jun", "jul"]


def test_notes_are_quoted_with_sources_and_noise_is_dropped() -> None:
    sections = [("Climate", "Winter – November to January is dry and cool. As of Nov 2023, the fare was ₹1500."),
                ("By bus", "Buses run in the monsoon from June to September every hour."),
                ("Understand", "The town has a pleasant climate for most of the year.")]  # fmt: skip
    by_month, general = notes_from(sections, "https://example.org/x")
    assert [n["text"] for n in by_month["dec"]] == ["Winter – November to January is dry and cool."]
    assert by_month["jun"] == []  # "By bus" is not a season section
    assert general == [{"text": "The town has a pleasant climate for most of the year.",
                        "source_url": "https://example.org/x", "kind": "general"}]  # fmt: skip


def test_every_destination_has_sourced_notes_for_october_to_january() -> None:
    for city in ("Mysuru", "Bengaluru", "Chikmagalur", "Coorg", "Goa"):
        for month in OCT_JAN:
            notes = notes_for(city, month)
            assert notes, (city, month)
            assert all(n["source_url"].startswith("https://en.wiki") for n in notes)
            for n in notes:
                if n["kind"] == "month":
                    assert MONTHS[month - 1] in months_in(n["text"])
    # Hampi: Wikivoyage and Wikipedia name only November (Hampi Utsav). No note is
    # better than an invented one; the gap is reported, not filled.
    assert notes_for("Hampi", 11) and notes_for("Hampi", 10) == []


def test_lookup_by_alias_and_by_date() -> None:
    assert notes_for("Panjim", date(2026, 12, 20)) == notes_for("Goa", 12)
    assert any("mid-November to mid-February" in n["text"] for n in notes_for("Goa", 12))
    assert notes_for("Kashmir", 12) == []
