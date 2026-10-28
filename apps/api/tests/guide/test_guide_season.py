from datetime import date

from guide.season import MONTHS, months_in, notes_for, notes_from

OCT_JAN = (10, 11, 12, 1)


def test_month_ranges_and_single_months() -> None:
    assert months_in("the monsoon (June to October)") == ["jun", "jul", "aug", "sep", "oct"]
    assert months_in("mid-November to mid-February") == ["jan", "feb", "nov", "dec"]
    assert months_in("Winter – November to January") == ["jan", "nov", "dec"]
    assert months_in("every year during the first week of November") == ["nov"]
    assert months_in("You may see rain any time") == []  # "may" the verb
    assert months_in("rain in March and October") == ["mar", "oct"]  # "and" joins two months, no range
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


# --- WA-02, WEB-09: season notes inside the trip dates ---


def test_no_dasara_lights_for_a_trip_after_dasara() -> None:
    from datetime import date

    from guide.season import is_event, notes_for_trip

    after = notes_for_trip("Mysuru", date(2026, 10, 31), date(2026, 11, 1))
    assert after and not any("illuminated" in n["text"] for n in after)
    assert not any(is_event(n) for n in after) and {n["kind"] for n in after} <= {"month", "general"}
    during = notes_for_trip("Mysore", date(2026, 10, 15), date(2026, 10, 18))
    assert any(is_event(n) and "illuminated" in n["text"] for n in during)
    assert len({n["text"] for n in during}) == len(during)  # each note once


def test_events_are_kept_only_on_known_dates() -> None:
    from datetime import date

    from guide.season import event_window, is_event, notes_for, notes_for_trip

    october = notes_for("Mysuru", 10)
    assert sum(map(is_event, october)) == 1  # still listed by month
    assert {n["kind"] for n in october} <= {"month", "general"}  # the contract's kinds only
    assert event_window("Mysore Palace is illuminated for Dasara", 2026) == (date(2026, 10, 11), date(2026, 10, 20))
    assert event_window("Mysore Palace is illuminated for Dasara", 2031) is None  # unknown year: left out
    assert not any(map(is_event, notes_for_trip("Mysuru", date(2031, 10, 1), date(2031, 10, 31))))
    hampi = notes_for_trip("Hampi", date(2026, 11, 3), date(2026, 11, 5))
    assert any("Hampi Utsav" in n["text"] for n in hampi)
    assert not any("Hampi Utsav" in n["text"] for n in notes_for_trip("Hampi", date(2026, 11, 20), date(2026, 11, 22)))


def test_a_trip_across_new_year_reads_both_years() -> None:
    from datetime import date

    from guide.season import notes_for_trip

    notes = notes_for_trip("Goa", date(2026, 12, 30), date(2027, 1, 2))
    assert notes and len({n["text"] for n in notes}) == len(notes)


# --- HQ P7: notes about the trip's actual weeks, no activity notes, no wrong season ---


def test_season_notes_fit_the_trips_dates() -> None:
    from guide.season import fits_trip

    best = {"text": "The best time of the year to visit Goa is mid-November to mid-February when "
                    "the weather is comfortable, dry and pleasant.", "kind": "month"}  # fmt: skip
    assert not fits_trip(best, date(2026, 11, 1), date(2026, 11, 5))  # before mid-November
    assert fits_trip(best, date(2026, 11, 14), date(2026, 11, 18))
    assert fits_trip(best, date(2027, 1, 10), date(2027, 1, 12))  # the range across New Year
    assert not fits_trip(best, date(2027, 2, 20), date(2027, 2, 24))
    diving = {"text": "Diving: the season is between mid-October to mid-May.", "kind": "month"}
    assert not fits_trip(diving, date(2026, 11, 14), date(2026, 11, 18))  # an activity, not the season
    monsoon = {"text": "Tourists can travel around the Coorg, enjoying the amazing natural beauty in the "
                       "monsoon season.", "kind": "general"}  # fmt: skip
    assert not fits_trip(monsoon, date(2026, 11, 1), date(2026, 11, 4))
    assert fits_trip(monsoon, date(2026, 7, 1), date(2026, 7, 4))
    climate = {"text": "Madikeri features a tropical highland climate as it has an elevation of 1,170 m.",
               "kind": "general"}  # fmt: skip
    assert fits_trip(climate, date(2026, 11, 1), date(2026, 11, 4))


def test_goa_early_november_has_no_diving_and_no_mid_november_notes() -> None:
    from guide.season import notes_for_trip

    texts = [n["text"] for n in notes_for_trip("Goa", date(2026, 11, 1), date(2026, 11, 4))]
    assert not any("Diving" in t or "mid-November" in t for t in texts), texts
    coorg = [n["text"] for n in notes_for_trip("Coorg", date(2026, 11, 1), date(2026, 11, 4))]
    assert not any("monsoon" in t for t in coorg), coorg
