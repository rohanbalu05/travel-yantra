"""Katha. Checker and pipeline-shape tests run anywhere; story tests need DATABASE_URL."""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import guide
from guide.katha import KathaRequest, checks, katha
from guide.katha.facts import NEED, Fact, fitting_length
from guide.katha.fake import FakeKathaModel
from guide.katha.pipeline import CONTRACT_LABELS, KathaFailed, parse, renumber

TASTE_GATE = Path(__file__).resolve().parents[4] / "data" / "katha" / "taste-gate"


def fact(n: int, url: str | None = None) -> Fact:
    return Fact(n=n, chunk_id=100 + n, city="Hampi", title=f"T{n}", body="B.", is_legend=False,
                source_name="S", source_url=url)  # fmt: skip


# --- the banned-phrase checker (rule 11) ---


@pytest.mark.parametrize("phrase", checks.BANNED)
def test_every_banned_phrase_is_caught(phrase) -> None:
    assert checks.slop(f"The temple, {phrase} the river, holds a stone bell.")


def test_banned_shapes_are_caught() -> None:
    assert checks.slop("Whether you're a pilgrim or a photographer, come at dawn.")
    assert checks.slop("It was a grand, majestic and beautiful palace.")
    assert checks.slop("Why did the king leave? Who stayed behind? Nobody knows.")
    assert checks.slop("The Bustling market.")  # any case
    assert checks.slop("It delves into history and boasted of gold.")  # inflected forms


def test_plain_good_writing_passes() -> None:
    text = (
        "Raya's queen walked this street at dawn. Look at the third pillar on your left: "
        "carved, painted and gilded lions still hold up the roof. Why here? The river was close."
    )
    assert checks.slop(text) == []
    assert checks.slop("Breathing slowly, she climbed.") == []  # 'breath' is not 'breathtaking'


def test_problems_catch_uncited_history_untold_legends_bad_markers_and_length() -> None:
    long = " ".join(["word"] * 300)
    assert checks.problems([("history", f"{long} [1].")], 2, 2) == []
    found = checks.problems([("history", long), ("legend", "A demon lived here [1]."),
                             ("history", "Fact [7].")], 2, 2)  # fmt: skip
    joined = " | ".join(found)
    assert "uncited history" in joined and "legend not told as legend" in joined
    assert "markers point at no fact: [7]" in joined
    assert "length" not in joined  # 304 words is inside the 2-minute band
    assert any("length" in p for p in checks.problems([("history", "Short [1].")], 1, 2))


def test_thin_sources_make_a_shorter_story() -> None:
    assert fitting_length(10, 30) == 10
    assert fitting_length(10, NEED[10] - 1) == 5
    assert fitting_length(5, NEED[5] - 1) == 2
    assert fitting_length(2, 1) == 0


def test_parse_and_renumber_share_sources_and_order_markers() -> None:
    text = "noise\n[HISTORY]\nA [3]. B [1].\n\nC [3][3].\n[LEGEND]\nPeople say D [2].\n[DISPUTED]\nE [1]."
    segments = parse(text)
    assert [s[0] for s in segments] == ["history", "history", "legend", "disputed"]
    facts = [fact(1, "https://a"), fact(2, "https://a"), fact(3)]
    out, sources = renumber(segments, facts)
    assert sources == ["T3 (S)", "https://a"]  # facts 1 and 2 share a URL, so a number
    assert [s.text for s in out] == ["A [1]. B [2].", "C [1].", "People say D [2].", "E [2]."]
    assert out[3].label == ("disputed" if "disputed" in CONTRACT_LABELS else "history")


# Real sentences from the taste-gate pack (Oct 2026), where combined markers went out
# unrenumbered: "[6, 14]" in a story with 7 sources pointed at fact numbers.
REAL = [
    "The floor beneath you is uneven, laid down in 1886 [1, 2], so watch your step.",
    "This event ended an empire, and the British took his iron-cased rockets and "
    "mechanical tiger back to England as trophies [7, 11, 12].",
    "They pack their remaining garlands under the shadow of the rusting iron pillars [3][4].",
    "The city's deepest historical wound lies sixteen kilometres north on the island of "
    "Srirangapatna, where the Kaveri river splits [6, 14].",
]


@pytest.mark.parametrize(
    ("marker", "numbers"),
    [("1, 2", [1, 2]), ("7, 11, 12", [7, 11, 12]), ("14, 6", [14, 6]), ("3-5", [3, 4, 5]),
     ("3–5", [3, 4, 5]), ("2, 4-6", [2, 4, 5, 6]), ("1, 1", [1]), ("1-40", [1, 40])],
)  # fmt: skip
def test_combined_markers_expand(marker, numbers) -> None:
    assert checks.cited(marker) == numbers


def test_checks_see_every_number_in_combined_markers() -> None:
    assert checks.citations(" ".join(REAL)) == [1, 2, 7, 11, 12, 3, 4, 6, 14]
    assert checks.words("laid down in 1886 [1, 2], so [3-5] watch [2][3]") == 6
    # [1, 2] is a citation: the history segment is cited, and 9 is out of range
    assert checks.problems([("history", REAL[0])], 2, 2) == [
        f"length {checks.words(REAL[0])} words, want 220-400 for 2 min"
    ]
    assert "markers point at no fact: [9]" in checks.problems([("history", "Fact [2, 9].")], 2, 2)[0]


def test_renumber_splits_combined_markers_into_sources() -> None:
    facts = [fact(n, "https://a" if n in (11, 12) else None) for n in range(1, 15)]
    segments = [("history", t) for t in REAL]
    out, sources = renumber(segments, facts)
    assert [s.text[-12:] for s in out] == [
        "[1][2], so watch your step."[-12:],
        "trophies [3][4]."[-12:],  # 11 and 12 share a source
        " pillars [5][6]."[-12:],
        "splits [7][8]."[-12:],
    ]
    assert len(sources) == 8 and sources[3] == "https://a"
    assert renumber([("history", "A [2, 2]. B [3-4][3].")], facts)[0][0].text == "A [1]. B [2][3]."
    for s in out:  # every number now points at a source
        assert all(1 <= n <= len(sources) for n in checks.citations(s.text))


# --- the taste-gate pack, when it is there: every Katha version passes the checker ---


@pytest.mark.parametrize("path", sorted(TASTE_GATE.glob("key/*/katha.json")), ids=lambda p: p.parent.name)
def test_taste_gate_katha_is_clean(path) -> None:
    story = json.loads(path.read_text(encoding="utf-8"))
    segments = [(s["label"], s["text"]) for s in story["segments"]]
    assert checks.slop(story["text"]) == []
    assert all(s["label"] in {"history", "legend", "disputed"} for s in story["segments"])
    for label, text in segments:
        if label == "legend":
            assert checks.LEGEND_CUES.search(text)


# --- with the seeded database and the fake model ---


class Counting(FakeKathaModel):
    def __init__(self) -> None:
        self.calls = 0

    async def json(self, *a, **k):
        self.calls += 1
        return await super().json(*a, **k)

    async def text(self, *a, **k):
        self.calls += 1
        return await super().text(*a, **k)


def run(db, model=None, **req):
    return asyncio.run(katha(KathaRequest(**req), db, model or Counting()))


@pytest.mark.parametrize("length", [2, 5, 10])
def test_place_stories_fit_their_length_and_label_legends(db, length) -> None:
    story = run(db, subject_kind="place", subject="Vittala Temple", length_min=length)
    assert story.length_min == length and story.subject == "Vittala Temple and Stone Chariot"
    low, high = checks.BANDS[length]
    assert low <= checks.words(story.text) <= high
    assert story.segments and story.sources
    for s in story.segments:
        markers = checks.citations(s.text)
        assert all(1 <= n <= len(story.sources) for n in markers)
        if s.label == "legend":
            assert checks.LEGEND_CUES.search(s.text)
        else:
            assert markers
    assert any(s.label == "legend" for s in story.segments)  # Vittala has a legend: the pillars


def test_city_and_day_stories(db) -> None:
    city = run(db, subject_kind="city", subject="Mysore", length_min=5)
    assert city.subject == "Mysuru" and city.subject_kind == "city"
    day = run(db, subject_kind="day", subject="Day 1, Mysuru", length_min=2,
              places=["mysuru-mysore-palace", "Chamundeshwari Temple", "Devaraja Market"])  # fmt: skip
    assert day.subject == "Day 1, Mysuru" and day.length_min == 2


def test_a_second_request_is_served_from_the_cache(db) -> None:
    db.execute("DELETE FROM katha_cache WHERE story->>'subject' = 'Devaraja Market'")
    first = Counting()
    a = run(db, first, subject_kind="place", subject="Devaraja Market", length_min=2)
    assert first.calls == 3  # outline, draft, critique
    again = Counting()
    b = run(db, again, subject_kind="place", subject="devaraja market", length_min=2)
    assert again.calls == 0 and a == b


def test_a_draft_that_keeps_failing_is_never_shipped(db) -> None:
    class Sloppy(FakeKathaModel):
        async def text(self, prompt, *a, **k):
            return (await super().text(prompt, *a, **k)).replace("[HISTORY]\n", "[HISTORY]\nA vibrant ")

    with pytest.raises(KathaFailed) as e:
        run(db, Sloppy(), subject_kind="place", subject="Hampi Bazaar", length_min=2)
    assert any("vibrant" in p for p in e.value.problems)


@pytest.fixture
def api(db):
    app = FastAPI()
    app.include_router(guide.router)
    app.dependency_overrides[guide.get_db] = lambda: db
    return TestClient(app)


def test_katha_over_http(api) -> None:
    r = api.post("/guide/katha", json={"subject_kind": "place", "subject": "mysuru-mysore-palace",
                                       "length_min": 2, "lang": "kn"})  # fmt: skip
    assert r.status_code == 200
    story = r.json()
    assert story["lang"] == "en" and story["subject"] == "Mysore Palace"
    assert {s["label"] for s in story["segments"]} <= {"history", "legend", "disputed"}
    r = api.post("/guide/katha", json={"subject_kind": "place", "subject": "Taj Mahal", "length_min": 2})
    assert r.status_code == 404 and r.json() == {"detail": "No story for that place yet."}
    assert api.post("/guide/katha", json={"subject_kind": "place", "subject": "x",
                                          "length_min": 3}).status_code == 422  # fmt: skip


def test_a_rewrite_that_was_cut_short_keeps_the_draft() -> None:
    from guide.katha.pipeline import _chapter

    class Truncating(FakeKathaModel):
        async def text(self, prompt, *a, **k):
            if prompt.startswith("Here is a draft"):
                return "scores\n=== \n[HISTORY]\nOnly this [1]."
            return "[HISTORY]\n" + " ".join(["word"] * 200) + " [1].\n\n- Peak at 2/3: a note"

    from guide.katha.facts import Subject
    from guide.katha.pipeline import Beat, Chapter, Outline

    outline = Outline(theme="t", hook="h", gap="g", people=[], bridge="b", peak="p", ending="e",
                      chapters=[Chapter(title="c", hook="h", gap="g",
                                        beats=[Beat(text="x", facts=[1], label="history")])])  # fmt: skip
    text, critique = asyncio.run(_chapter(Truncating(), Subject(kind="place", name="X"), 2,
                                          outline, 0, [fact(1)], 230))  # fmt: skip
    assert "Only this" not in text and "rewrite not used" in critique
    assert parse(text) == [("history", " ".join(["word"] * 200) + " [1].")]  # the note is dropped


def test_a_goa_place_gets_a_story(db) -> None:
    story = run(db, subject_kind="place", subject="goa-basilica-of-bom-jesus", length_min=2)
    assert story.subject == "Basilica of Bom Jesus" and story.sources
    assert all("wikipedia.org" in s for s in story.sources)
