import json

from fastapi.testclient import TestClient

from core import steps
from guide.season import notes_for
from main import app
from ty_contracts import Itinerary, TripRequest

client = TestClient(app)


def plan(body) -> Itinerary:
    events = [json.loads(line[6:]) for line in client.post("/plan", json=body).text.splitlines() if line.startswith("data: ")]
    return Itinerary.model_validate(events[-1]["partial"])


def test_a_trip_carries_its_quoted_season_notes_with_sources():
    it = plan({"origin": "Bengaluru", "destinations": ["Mysuru"], "start_date": "2026-10-31", "end_date": "2026-11-01"})
    expected = {n["text"] for n in notes_for("Mysuru", 10)} | {n["text"] for n in notes_for("Mysuru", 11)}
    assert it.season_notes and {n.text for n in it.season_notes} == expected
    assert all(n.city == "Mysuru" and n.source_url.startswith("https://") for n in it.season_notes)
    assert len({n.text for n in it.season_notes}) == len(it.season_notes)  # no repeats across the two months


def test_nothing_is_added_when_the_sources_say_nothing():
    r = TripRequest.model_validate({"origin": "Bengaluru", "destinations": ["Hampi"], "start_date": "2026-12-01",
                                    "end_date": "2026-12-02"})
    assert notes_for("Hampi", 12) == [] and steps.season_notes(r) == []


def test_each_city_gets_notes_for_its_own_dates():
    r = TripRequest.model_validate({"origin": "Bengaluru", "destinations": ["Mysuru", "Coorg"],
                                    "start_date": "2026-11-20", "end_date": "2026-11-24"})
    notes = steps.season_notes(r)
    assert {n.city for n in notes} <= {"Mysuru", "Coorg"}
    assert [n.text for n in notes if n.city == "Coorg"] == [n["text"] for n in notes_for("Coorg", 11)]
