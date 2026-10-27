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
EVAL_FILE = Path(__file__).parent / "eval_ask.jsonl"
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
    assert "Sample Hospital One, 1.1 km [1]" in answer.text
    assert "query_place_id=sample-hospital-1" in answer.citations[0].url


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
    if expect == "emergency":
        assert transport.kinds == case["places"]
        assert answer.emergency_places and "112" in answer.text
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
    assert data["citations"][0]["title"] == "Google Maps: Sample Hospital One"


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
