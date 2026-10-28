"""/guide/ask. Pure tests run anywhere; the eval and endpoint tests need DATABASE_URL."""

import asyncio
import importlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import guide
from guide.ask import (
    REFUSAL,
    FakeAnswerer,
    answer_emergency,
    ask,
    build_prompt,
    emergency_kinds,
    ground,
)
from guide.places import MemoryCache, PlacesClient
from guide.retrieval.retrieve import Hit
from ty_contracts import GuideQuestion

ask_mod = importlib.import_module("guide.ask")  # guide.ask the function shadows it
EVAL_FILE = Path(__file__).resolve().parents[2] / "guide" / "eval" / "eval_ask.jsonl"
EVAL = [json.loads(line) for line in EVAL_FILE.read_text(encoding="utf-8").splitlines()]


def hit(n: int, *, legend: bool = False, body: str = "Fact one. Fact two.") -> Hit:
    return Hit(
        id=n, poi_id=None, city="Mysuru", title=f"Title {n}", body=body,
        chunk_type="story" if legend else "fact", is_legend=legend,
        source_name="Sample source", source_url=f"https://example.org/{n}",
        score=1.0, retrievers=["lexical"],
    )  # fmt: skip


class FakeNearby:
    """Places transport: one sample place per requested type, and a call log."""

    def __init__(self, fail: bool = False) -> None:
        self.kinds: list[str] = []
        self.fail = fail

    def __call__(self, method, url, headers, body, timeout):
        assert url.endswith("/places:searchNearby")
        if self.fail:
            raise OSError("network down")
        (kind,) = body["includedTypes"]
        self.kinds.append(kind)
        c = body["locationRestriction"]["circle"]["center"]
        return {"places": [{
            "id": f"sample-{kind}-1", "types": [kind],
            "location": {"latitude": c["latitude"] + 0.01, "longitude": c["longitude"]},
            "displayName": {"text": f"Sample {kind.title()} One"},
        }]}  # fmt: skip


def places(fail: bool = False) -> tuple[PlacesClient, FakeNearby]:
    t = FakeNearby(fail)
    return PlacesClient(cache=MemoryCache(), transport=t, api_key="test-key"), t


class Spy:
    """An answerer that replies with fixed text, or fails if it is asked at all."""

    def __init__(self, reply: str | None = None) -> None:
        self.reply = reply
        self.calls = 0

    async def __call__(self, question, sources):
        self.calls += 1
        assert self.reply is not None, "the model was asked an emergency question"
        return self.reply


class NoRows:
    def execute(self, *a, **k):
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []


def test_emergency_words_pick_the_right_kinds() -> None:
    assert emergency_kinds("Where is the nearest hospital?") == ["hospital"]
    assert emergency_kinds("my phone was stolen") == ["police"]
    assert emergency_kinds("is there a chemist open") == ["pharmacy"]
    assert emergency_kinds("snake bite, need medicine") == ["pharmacy", "hospital"]
    assert emergency_kinds("who built Mysore Palace") == []


def test_ground_renumbers_drops_bad_markers_and_builds_citations() -> None:
    sources = [hit(1), hit(2), hit(3)]
    answer = ground("Third fact [3]. First fact [1, 3]. Made up [9].", sources)
    assert answer.text == "Third fact [1]. First fact [2][1]. Made up."
    assert [c.url for c in answer.citations] == ["https://example.org/3", "https://example.org/1"]
    assert answer.citations[0].title == "Title 3 (Sample source)"


def test_ground_refuses_uncited_and_no_answer_replies() -> None:
    assert ground("Mysuru is lovely.", [hit(1)]) is None
    assert ground("NO_ANSWER", [hit(1)]) is None
    assert ground("Only a bad marker [4].", [hit(1)]) is None


def test_prompt_numbers_sources_and_marks_legends() -> None:
    prompt = build_prompt("q?", [hit(1), hit(2, legend=True)])
    assert "[1] [Mysuru] Title 1" in prompt and "[2] (legend) [Mysuru] Title 2" in prompt
    assert prompt.rstrip().endswith("Question: q?")


def test_fake_answerer_labels_legends_and_cites() -> None:
    text = asyncio.run(FakeAnswerer()("q", [hit(1), hit(2, legend=True)]))
    assert text == "Fact one [1]. Legend says Fact one [2]."


def test_emergency_without_a_location_gives_the_number_and_no_places() -> None:
    client, transport = places()
    answer = answer_emergency(["hospital"], None, client)
    assert "112" in answer.text and not answer.emergency_places and not transport.kinds


def test_emergency_when_places_fails_says_so_and_invents_nothing() -> None:
    client, _ = places(fail=True)
    answer = answer_emergency(["police"], (12.3, 76.6), client)
    assert "couldn't reach Google Maps" in answer.text
    assert not answer.emergency_places and not answer.citations


def test_an_emergency_never_reaches_the_model() -> None:
    client, transport = places()
    spy = Spy()
    req = GuideQuestion(question="need an ambulance", lat=12.3, lng=76.65)
    answer = asyncio.run(ask(req, NoRows(), spy, client))
    assert spy.calls == 0 and transport.kinds == ["hospital"]
    (place,) = answer.emergency_places
    assert place.name == "Sample Hospital One" and place.source == "google_places"
    assert "Sample Hospital One (1.1 km)" in answer.text and not answer.citations


def test_no_hits_and_uncited_answers_become_the_refusal() -> None:
    req = GuideQuestion(question="anything")
    none = asyncio.run(ask(req, NoRows(), Spy("x [1]"), retrieve=lambda *a, **k: []))
    assert none.text == REFUSAL and not none.citations
    uncited = asyncio.run(
        ask(req, NoRows(), Spy("Sure, it is great."), retrieve=lambda *a, **k: [hit(1)])
    )
    assert uncited.text == REFUSAL


def test_fake_llm_env_selects_the_fake(monkeypatch) -> None:
    monkeypatch.setenv("TY_FAKE_LLM", "1")
    assert isinstance(ask_mod.answerer(), FakeAnswerer)
    monkeypatch.setenv("TY_FAKE_LLM", "0")
    assert isinstance(ask_mod.answerer(), ask_mod.ModelAnswerer)


def test_no_database_is_503_and_bad_input_is_422(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = FastAPI()
    app.include_router(guide.router)
    r = TestClient(app).post("/guide/ask", json={"question": "hello"})
    assert r.status_code == 503 and r.json() == {"detail": "The guide is offline right now."}
    app.dependency_overrides[guide.get_db] = NoRows
    for bad in ({"question": ""}, {"question": "x" * 501}, {"question": "q", "lat": 91}, {}):
        assert TestClient(app).post("/guide/ask", json=bad).status_code == 422


# With the seeded database: fake embedder, fake answerer, fake Places.


@pytest.mark.parametrize("case", EVAL, ids=[f"{c['kind']}:{c['question'][:30]}" for c in EVAL])
def test_eval_set(db, case) -> None:
    client, transport = places()
    fields = {k: case[k] for k in ("question", "city", "place_name", "lat", "lng") if k in case}
    answer = asyncio.run(ask(GuideQuestion(**fields), db, FakeAnswerer(), client))
    expect = case["expect"]
    if expect == "refusal":
        assert answer.text == REFUSAL and not answer.citations
        return
    if expect in ("emergency", "nearby"):  # nearby: everyday help, no 112 header (HQ P8)
        assert transport.kinds == case["places"]
        assert answer.emergency_places and ("112" in answer.text) == (expect == "emergency")
        assert {p.id for p in answer.emergency_places} == {f"sample-{k}-1" for k in case["places"]}
        return
    assert answer.citations and not answer.emergency_places and not transport.kinds
    titles = [c.title for c in answer.citations]
    assert any(t.startswith(case["title"]) for t in titles), titles
    assert "[1]" in answer.text
    if expect == "legend":
        assert "Legend says" in answer.text


@pytest.fixture
def api(db):
    client, transport = places()
    app = FastAPI()
    app.include_router(guide.router)
    app.dependency_overrides[guide.get_db] = lambda: db
    app.dependency_overrides[guide.get_places] = lambda: client
    return TestClient(app), transport


SAMPLES = [
    ({"question": "the battle of Talikota"}, "Six months of burning"),
    ({"question": "who invented Mysore pak"}, "The sweet invented in this"),
    ({"question": "Dasara procession", "city": "Mysuru"}, "The Dasara procession"),
    ({"question": "the pillars that play music"}, "The pillars that play"),
]


@pytest.mark.parametrize(("body", "title"), SAMPLES, ids=["history", "food", "culture", "legend"])
def test_sample_questions_over_http(api, body, title) -> None:
    client, _ = api
    r = client.post("/guide/ask", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["lang"] == "en" and data["emergency_places"] == []
    assert any(c["title"].startswith(title) for c in data["citations"])


def test_sample_emergency_over_http(api) -> None:
    client, transport = api
    body = {"question": "nearest hospital please", "place_name": "Chamundeshwari Temple"}
    r = client.post("/guide/ask", json=body)
    assert r.status_code == 200
    data = r.json()
    assert transport.kinds == ["hospital"]
    assert [p["name"] for p in data["emergency_places"]] == ["Sample Hospital One"]
    assert data["citations"] == []  # the places are listed once, with their map links


def test_a_failing_model_is_503_with_a_reason(monkeypatch) -> None:
    class Broken:
        calls = 0

        async def __call__(self, question, sources):
            Broken.calls += 1
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(ask_mod, "search", lambda *a, **k: [hit(1)])
    app = FastAPI()
    app.include_router(guide.router)
    app.dependency_overrides[guide.get_db] = NoRows
    app.dependency_overrides[guide.answerer] = Broken
    r = TestClient(app).post("/guide/ask", json={"question": "who built it"})
    assert r.status_code == 503 and r.json() == {"detail": guide.BUSY}
    assert Broken.calls == 1  # it failed in the model, not somewhere earlier


def test_warm_up_never_loads_the_model_under_the_fake(monkeypatch) -> None:
    from guide.retrieval import embed

    monkeypatch.setattr(embed, "model", lambda: pytest.fail("loaded the real model"))
    guide.warm_up()  # EMBEDDER=fake in tests: the corpus warms, the model does not


def test_city_is_a_soft_hint() -> None:
    seen = []

    def retrieve(q, db, *, filters, k, trip_context):
        seen.append(filters.city if filters else None)
        return [hit(1)] if filters is None else []

    req = GuideQuestion(question="Who built Mysore Palace?", city="Mysore")
    answer = asyncio.run(ask(req, NoRows(), Spy("Built by a king [1]."), retrieve=retrieve))
    assert seen == ["Mysuru", None] and answer.citations  # narrowed first, then everywhere
    seen.clear()
    asyncio.run(ask(GuideQuestion(question="q", city="Kashmir"), NoRows(), Spy("x [1]."), retrieve=retrieve))
    assert seen == [None]  # not a corpus city: no filter at all


def test_a_plan_in_goa_still_answers_about_mysuru(db) -> None:
    req = GuideQuestion(question="who invented Mysore pak", city="Goa")
    answer = asyncio.run(ask(req, db, FakeAnswerer(), places()[0]))
    # Goa is a corpus city now: the Goa-only search must refuse and fall back, not cite Goa.
    assert any(c.title.startswith("The sweet") for c in answer.citations), answer.citations


def test_goa_questions_answer_from_the_corridor(db) -> None:
    answer = asyncio.run(ask(GuideQuestion(question="Basilica of Bom Jesus Francis Xavier", city="Goa"),
                             db, FakeAnswerer(), places()[0]))  # fmt: skip
    assert answer.citations and all("wikipedia.org" in (c.url or "") for c in answer.citations)


# --- cardiac or injury: full hospitals before clinics (sample names, Panaji-like layout) ---

NEAR_PANAJI = [  # (name, primaryType, km north of the traveller), as Places lists them: nearest first
    ("Sample Urban Health Centre", "hospital", 0.2),
    ("Sample Nursing Home Hospital", "hospital", 0.3),
    ("Dr. Sample Clinic", "doctor", 0.4),
    ("Sample Town Hospital", "hospital", 1.5),
    ("Sample Medical College and Hospital", "hospital", 7.0),
]


class Crowded:
    def __init__(self) -> None:
        self.bodies: list[dict] = []

    def __call__(self, method, url, headers, body, timeout):
        self.bodies.append(body)
        c = body["locationRestriction"]["circle"]["center"]
        return {"places": [{
            "id": f"sample-{i}", "types": [kind, "health"], "primaryType": kind,
            "location": {"latitude": c["latitude"] + km / 111.2, "longitude": c["longitude"]},
            "displayName": {"text": name},
        } for i, (name, kind, km) in enumerate(NEAR_PANAJI)]}  # fmt: skip


def crowded():
    t = Crowded()
    return PlacesClient(cache=MemoryCache(), transport=t, api_key="test-key"), t


def test_care_tier_reads_names_and_primary_type() -> None:
    from guide.ask import care_tier
    from ty_contracts import Place

    def p(name, category="hospital"):
        return Place(id="x", name=name, lat=0, lng=0, category=category, typical_visit_minutes=0, source="t")

    assert care_tier(p("Sample District Hospital")) == 0
    assert care_tier(p("Sample Multispeciality Hospital")) == 0
    assert care_tier(p("Sample Town Hospital")) == 1
    assert care_tier(p("Sample Nursing Home Hospital")) == 2
    assert care_tier(p("Sample Urban Health Centre")) == 3
    assert care_tier(p("Dr. Sample", "doctor")) == 3 and care_tier(p("Sample Clinic")) == 3
    # a big name on small care is still small care; short chain names match whole words only
    assert care_tier(p("Apollo Clinic", "medical_clinic")) == 3
    assert care_tier(p("Sample Heart Clinic")) == 3 and care_tier(p("Max Lab", "medical_lab")) == 3
    assert care_tier(p("Apollo Hospitals")) == 0 and care_tier(p("Sample Masters Hospital")) == 1
    assert care_tier(p("Sample Clinic and Hospital")) == 2
    # seen live near Panaji: a pharmacy typed medical_center ranked first under the old regex
    assert care_tier(p("Pharmax Medical Stores", "medical_center")) == 3
    assert care_tier(p("Apollo Hospital Pharmacy")) == 3 and care_tier(p("Sample Lab", "medical_lab")) == 3
    assert care_tier(p("Dr. Sample Memorial Hospital")) == 1
    assert care_tier(p("Sample Medical College Hospital & Diagnostic Centre")) == 0


def test_chest_pain_ranks_full_hospitals_above_nearer_clinics() -> None:
    client, t = crowded()
    req = GuideQuestion(question="My father has chest pain, where is the nearest hospital?",
                        lat=15.4983, lng=73.8294)  # fmt: skip
    answer = asyncio.run(ask(req, NoRows(), Spy(), client))
    names = [p.name for p in answer.emergency_places]
    assert names == ["Sample Medical College and Hospital", "Sample Town Hospital",
                     "Sample Nursing Home Hospital"]  # fmt: skip
    assert "full hospital" in answer.text and "(7.0 km)" in answer.text and "112" in answer.text
    body = t.bodies[0]
    assert body["maxResultCount"] == 20 and body["locationRestriction"]["circle"]["radius"] == 15000
    assert body["rankPreference"] == "POPULARITY"  # big hospitals a few km out, not the nearest 20


@pytest.mark.parametrize("question", ["He fell and is bleeding badly", "road accident near us",
                                      "snakebite, which hospital?"])  # fmt: skip
def test_injuries_are_urgent_too(question) -> None:
    client, _ = crowded()
    answer = asyncio.run(ask(GuideQuestion(question=question, lat=15.5, lng=73.8), NoRows(), Spy(), client))
    assert answer.emergency_places[0].name == "Sample Medical College and Hospital"


def test_a_plain_hospital_question_also_lists_hospitals_before_clinics() -> None:
    # WA-19 (live, 28 Oct): "hospital near Panaji" listed a clinic and a health centre first.
    client, t = crowded()
    answer = asyncio.run(ask(GuideQuestion(question="Where is the nearest hospital?", lat=15.5, lng=73.8),
                             NoRows(), Spy(), client))  # fmt: skip
    assert answer.emergency_places[0].name == "Sample Medical College and Hospital"
    assert "Sample Urban Health Centre" not in [p.name for p in answer.emergency_places]
    assert "full hospital" not in answer.text and "larger ones first" in answer.text
    assert t.bodies[0]["maxResultCount"] == 20 and "112" in answer.text and "108" in answer.text


# --- "hospital near Panaji" with no location: the named place, not the city's middle ---


@pytest.mark.parametrize(("question", "name"), [
    ("hospital near Panaji", "Panaji"), ("Hospital near Panaji?", "Panaji"),
    ("chest pain, hospital near Old Goa please", "Old Goa"), ("police station in Calangute", "Calangute"),
    ("ambulance near the Basilica of Bom Jesus", "Basilica of Bom Jesus"),
    ("nearest hospital", None), ("pharmacy near me", None), ("hospital near my hotel", None),
    ("in an emergency what do I do", None),
    # review round 2: times, vehicles and generic places are never names
    ("I need a doctor at night", None), ("chest pain in the car", None), ("help in the morning", None),
    ("accident at the airport", None), ("stolen at the station", None),
    ("ambulance at my hotel in Panaji", "Panaji"),  # a later preposition still counts
    ("hospital near panaji", "panaji"),  # a corpus city, however it is written
    ("hospital near calangute", None),  # lowercase and not a corpus city: not trusted
])  # fmt: skip
def test_named_place(question, name) -> None:
    assert ask_mod.named_place(question) == name


class Geocode:
    """Text Search answers with Panaji; Nearby answers with one sample hospital there."""

    def __init__(self) -> None:
        self.searched: list[str] = []
        self.centres: list[tuple[float, float]] = []

    def __call__(self, method, url, headers, body, timeout):
        if url.endswith("/places:searchText"):
            self.searched.append(body["textQuery"])
            return {"places": [{"id": "sample-panaji", "types": ["locality"],
                                "location": {"latitude": 15.4909, "longitude": 73.8278},
                                "displayName": {"text": "Panaji"}}]}  # fmt: skip
        c = body["locationRestriction"]["circle"]["center"]
        self.centres.append((c["latitude"], c["longitude"]))
        return {"places": [{"id": "sample-h", "types": ["hospital"], "primaryType": "hospital",
                            "location": {"latitude": c["latitude"], "longitude": c["longitude"] + 0.005},
                            "displayName": {"text": "Sample Hospital"}}]}  # fmt: skip


class CityOnly:
    """No poi matches the name; the city centre would be the middle of Goa."""

    def execute(self, sql, params=()):
        class R:
            def fetchone(self):
                return (15.35, 74.05) if "avg(lat)" in sql else None

            def fetchall(self):
                return []

        return R()


def test_hospital_near_panaji_without_a_location_searches_at_panaji() -> None:
    t = Geocode()
    client = PlacesClient(cache=MemoryCache(), transport=t, api_key="test-key")
    req = GuideQuestion(question="hospital near Panaji", city="Goa")
    answer = asyncio.run(ask(req, CityOnly(), Spy(), client))
    assert t.searched == ["Panaji, India"] and t.centres == [(15.4909, 73.8278)]
    assert "Hospitals near Panaji, larger ones first: Sample Hospital (0.5 km)." in answer.text


def test_a_named_place_google_cannot_find_falls_back_to_the_city() -> None:
    client, transport = places(fail=True)  # every Places call fails
    req = GuideQuestion(question="hospital near Nowhereville", city="Goa")
    answer = asyncio.run(ask(req, CityOnly(), Spy(), client))
    assert "couldn't reach Google Maps" in answer.text  # located (city), then nearby failed


def test_a_places_match_far_from_the_trip_is_ignored() -> None:
    class FarAway(Geocode):
        def __call__(self, method, url, headers, body, timeout):
            out = super().__call__(method, url, headers, body, timeout)
            if url.endswith("/places:searchText"):  # a "Panaji" business in another state
                out["places"][0]["location"] = {"latitude": 28.61, "longitude": 77.21}
            return out

    t = FarAway()
    client = PlacesClient(cache=MemoryCache(), transport=t, api_key="test-key")
    asyncio.run(ask(GuideQuestion(question="hospital near Panaji", city="Goa"), CityOnly(), Spy(), client))
    assert t.centres == [(15.35, 74.05)]  # the trip's city, not Delhi


# --- HQ P7/P8: clean names, no talk about sources, everyday help nearby ---


@pytest.mark.parametrize(("raw", "clean"), [
    ("Sample Hospital | Multispeciality Hospital in Bengaluru", "Sample Hospital"),
    ("Sample Dental Clinic - Best Dentist in Panaji", "Sample Dental Clinic"),
    ("Sample Hospital - Old Airport Road", "Sample Hospital - Old Airport Road"),  # a branch stays
    ("Sample Cafe – Top Restaurant In Kochi", "Sample Cafe"),
    ("Sample Pharmacy", "Sample Pharmacy"),
    ("Sample Tiffin Room (STR) - Vegetarian Restaurant", "Sample Tiffin Room (STR)"),  # live, Mysuru
    ("Sample Hotel Since 1982 - Gandhi Square", "Sample Hotel Since 1982 - Gandhi Square"),
])  # fmt: skip
def test_clean_name_drops_listing_ad_copy(raw, clean) -> None:
    assert ask_mod.clean_name(raw) == clean


def test_answers_never_talk_about_their_sources() -> None:
    sources = [hit(1), hit(2)]
    answer = ground("Based on the provided sources, the palace burned in 1897 [1]. "
                    "The sources do not provide the architect's fee. It was rebuilt in stone [2].", sources)  # fmt: skip
    assert answer.text == "The palace burned in 1897 [1]. It was rebuilt in stone [2]."
    only_gap = ground("The provided sources don't say who built it [1].", sources)
    assert only_gap is None  # nothing left but the gap: the plain refusal


class Typed:
    """Places Nearby: two sample places of the requested type, the second one nearer."""

    def __init__(self) -> None:
        self.bodies: list[dict] = []

    def __call__(self, method, url, headers, body, timeout):
        self.bodies.append(body)
        (kind,) = body["includedTypes"]
        c = body["locationRestriction"]["circle"]["center"]
        return {"places": [{
            "id": f"sample-{kind}-{i}", "types": [kind], "primaryType": kind,
            "location": {"latitude": c["latitude"] + d / 111.2, "longitude": c["longitude"]},
            "displayName": {"text": name},
        } for i, (name, d) in enumerate([(f"Sample {kind} Far | Best {kind} in Kochi", 0.9),
                                          (f"Sample {kind} Near", 0.2)])]}  # fmt: skip


@pytest.mark.parametrize(("question", "kind"), [
    ("any veg restaurants near here?", "vegetarian_restaurant"),
    ("pure vegetarian food nearby", "vegetarian_restaurant"),
    ("where can we eat dinner nearby", "restaurant"),
    ("non-veg restaurants around", "restaurant"),
    ("nearest ATM", "atm"), ("I need cash", "atm"),
    ("pharmacy near me", "pharmacy"), ("where can I buy medicine", "pharmacy"),
])  # fmt: skip
def test_everyday_help_lists_nearby_places_without_the_emergency_header(question, kind) -> None:
    t = Typed()
    client = PlacesClient(cache=MemoryCache(), transport=t, api_key="test-key")
    answer = asyncio.run(ask(GuideQuestion(question=question, lat=9.96, lng=76.24), NoRows(), Spy(), client))
    assert [b["includedTypes"] for b in t.bodies] == [[kind]]
    assert [p.name for p in answer.emergency_places] == [f"Sample {kind} Near", f"Sample {kind} Far"]
    assert "112" not in answer.text and not answer.citations
    assert f"Sample {kind} Near (0.2 km); Sample {kind} Far (0.9 km)" in answer.text


def test_a_food_question_without_near_or_a_location_goes_to_the_guide() -> None:
    answer = asyncio.run(ask(GuideQuestion(question="What food is Udupi known for?"), NoRows(),
                             Spy("Dosa [1]."), retrieve=lambda *a, **k: [hit(1)]))  # fmt: skip
    assert answer.text == "Dosa [1]." and not answer.emergency_places


def test_an_overdose_is_an_emergency_not_an_errand() -> None:
    client, transport = places()
    answer = asyncio.run(ask(GuideQuestion(question="my son swallowed tablets", lat=9.96, lng=76.24),
                             NoRows(), Spy(), client))  # fmt: skip
    assert "112" in answer.text and transport.kinds == ["pharmacy"]


def test_nearby_help_without_a_location_asks_for_one() -> None:
    answer = asyncio.run(ask(GuideQuestion(question="nearest ATM"), NoRows(), Spy(), places()[0]))
    assert "Share your location" in answer.text and not answer.emergency_places


def test_nearby_endpoint_lists_clean_places_with_map_links() -> None:
    t = Typed()
    client = PlacesClient(cache=MemoryCache(), transport=t, api_key="test-key")
    app = FastAPI()
    app.include_router(guide.router)
    app.dependency_overrides[guide.get_places] = lambda: client
    r = TestClient(app).get("/guide/nearby", params={"lat": 9.96, "lng": 76.24, "kind": "veg", "limit": 2})
    assert r.status_code == 200
    data = r.json()
    assert [d["name"] for d in data] == ["Sample vegetarian_restaurant Near", "Sample vegetarian_restaurant Far"]
    assert data[0]["kind"] == "veg" and data[0]["distance_m"] == 200 and "query_place_id=" in data[0]["maps_url"]
    assert t.bodies[0]["includedTypes"] == ["vegetarian_restaurant"]
    assert TestClient(app).get("/guide/nearby", params={"lat": 9.96, "lng": 76.24, "kind": "bar"}).status_code == 422


# --- HQ P9: hours from Google Maps or none at all; never guessed ---


def test_hours_are_grouped_and_closed_days_named() -> None:
    from datetime import time as t

    from ty_contracts.models import OpeningHours

    week = [OpeningHours(day=d, opens=t(6), closes=t(18, 30)) for d in ("sat", "sun", "mon", "tue", "wed", "thu")]
    assert ask_mod.format_hours(week) == "Mon-Thu 06:00-18:30; Sat-Sun 06:00-18:30; closed Fri"


@pytest.mark.parametrize(("question", "name"), [
    ("When does the Taj Mahal open?", "Taj Mahal"), ("ताजमहल कितने बजे खुलता है?", "Taj Mahal"),
    ("Is Hawa Mahal open on Monday?", "Hawa Mahal"), ("Who built the Taj Mahal?", None),
    ("मुगल समय में ताजमहल कैसा था?", None),
])  # fmt: skip
def test_hours_questions_name_their_place(question, name) -> None:
    poi = ask_mod.asked_place(question, None) if ask_mod.HOURS_Q.search(question) else None
    assert (poi["name"] if poi else None) == name


def test_a_place_without_hours_is_told_to_check_never_guessed(monkeypatch) -> None:
    import guide.hours

    monkeypatch.setattr(guide.hours, "live_hours", lambda places, *a, **k: places)  # Places has none
    poi = ask_mod.asked_place("is Anamudi open today?", None)
    answer = asyncio.run(ask(GuideQuestion(question="is Anamudi open today?"), NoRows(), Spy()))
    assert poi and answer.text == f"I don't have reliable opening hours for {poi['name']}. Check hours before you go."
