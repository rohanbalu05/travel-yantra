"""Katha. Checker and pipeline-shape tests run anywhere; story tests need DATABASE_URL."""

import asyncio
import json
import re
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
    assert sources == ["S", "https://a"]  # facts 1 and 2 share a URL, so a number; 3 is named
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
    facts = [fact(n, "https://a" if n in (11, 12) else f"https://s/{n}") for n in range(1, 15)]
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
    assert story["lang"] == "kn" and story["subject"] == "Mysore Palace"  # Kannada has a voice
    assert {s["label"] for s in story["segments"]} <= {"history", "legend", "disputed"}
    r = api.post("/guide/katha", json={"subject_kind": "place", "subject": "Mysore Palace",
                                       "length_min": 2, "lang": "ta"})  # fmt: skip
    assert r.status_code == 200 and r.json()["lang"] == "en"  # no Tamil voice: English for translate
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
                                          outline, 0, [fact(1)], 230, "en"))  # fmt: skip
    assert "Only this" not in text and "rewrite not used" in critique
    assert parse(text) == [("history", " ".join(["word"] * 200) + " [1].")]  # the note is dropped


def test_a_goa_place_gets_a_story(db) -> None:
    story = run(db, subject_kind="place", subject="goa-basilica-of-bom-jesus", length_min=2)
    assert story.subject == "Basilica of Bom Jesus" and story.sources
    assert all("wikipedia.org" in s for s in story.sources)


# --- the trim step: an over-long story is cut once, inside its band, before the checks ---


class LongWinded(FakeKathaModel):
    """Drafts about 560 words for a 2-minute story, like the live model did."""

    def __init__(self, trims: bool = True) -> None:
        self.trims, self.labels = trims, []

    async def json(self, *a, **k):
        self.labels.append(k.get("label"))
        return await super().json(*a, **k)

    async def text(self, prompt, tier="flash", **k):
        self.labels.append(k.get("label"))
        if prompt.startswith("This spoken story") and not self.trims:
            return prompt.split("Story:\n\n", 1)[1]  # "cut" that changes nothing
        return await super().text(prompt.replace("between 242 and", "between 560 and"), tier, **k)


def long_facts() -> list[Fact]:
    bodies = ["The stone bell by the east gate was cast in 1886 for the river festival.",
              "Flower sellers here string Mysore mallige jasmine before the sun is up.",
              "Iron pillars brought by rail still hold up the old market roof."]  # fmt: skip
    return [Fact(n=i + 1, chunk_id=200 + i, city="Mysuru", title=f"T{i}", body=b,
                 is_legend=False, source_name="S", source_url=f"https://s/{i}")
            for i, b in enumerate(bodies)]  # fmt: skip


def test_an_over_long_story_is_trimmed_into_its_band() -> None:
    from guide.katha.facts import Subject
    from guide.katha.pipeline import write

    model = LongWinded()
    subject = Subject(kind="place", name="Devaraja Market", city="Mysuru", poi_ids=[1])
    story, notes = asyncio.run(write(model, subject, 2, long_facts()))
    low, high = checks.BANDS[2]
    assert low <= checks.words(story.text) <= high
    before, after = (int(n) for n in re.findall(r"\d+", notes["trim"]))
    assert notes["trim"].startswith("trimmed") and before > high >= after
    assert model.labels == ["katha outline", "katha draft", "katha critique", "katha trim"]


def test_a_trim_that_misses_the_band_is_never_shipped() -> None:
    from guide.katha.facts import Subject
    from guide.katha.pipeline import write

    subject = Subject(kind="place", name="Devaraja Market", city="Mysuru", poi_ids=[1])
    with pytest.raises(KathaFailed) as e:
        asyncio.run(write(LongWinded(trims=False), subject, 2, long_facts()))
    assert any("length" in p for p in e.value.problems)


def test_cache_key_hashes_exactly_its_logged_inputs() -> None:
    import hashlib

    from guide.katha import PIPELINE_VERSION, cache_key, key_inputs

    req = KathaRequest(subject_kind="place", subject="mysore palace ", length_min=2)
    inputs = key_inputs(req, "Mysore Palace", [3, 1])
    assert inputs == [PIPELINE_VERSION, "place", "Mysore Palace", 2, [3, 1]]
    assert cache_key(req, "Mysore Palace", [3, 1]) == hashlib.sha256(
        json.dumps(inputs, sort_keys=True).encode()).hexdigest()  # fmt: skip
    # the request's spelling never reaches the key; the resolved name does
    other = KathaRequest(subject_kind="place", subject="Mysore Palace", length_min=2)
    assert cache_key(other, "Mysore Palace", [3, 1]) == cache_key(req, "Mysore Palace", [3, 1])


# --- a second language from the same outline (rule 12), Hindi first ---


@pytest.mark.parametrize("phrase", checks.BANNED_LANG["hi"])
def test_every_hindi_banned_phrase_is_caught(phrase) -> None:
    assert phrase in checks.slop(f"मंदिर {phrase} और नदी के पास एक पत्थर की घंटी है।", "hi")


def test_hindi_checks_keep_the_english_ones_and_count_devanagari_words() -> None:
    assert checks.slop("यह एक hidden gem है।", "hi")  # English slop leaking into Hindi
    assert checks.slop("राजा सुबह नदी तक पैदल गए।", "hi") == []
    assert checks.words("मैसूर का महल 1912 में बना [1, 2]।", "hi") == 6
    assert checks.legend_told("लोग कहते हैं कि यहाँ एक राक्षस रहता था [1]।", "hi")
    assert checks.legend_told("कहा जाता है कि खंभे गाते हैं।", "hi")
    found = checks.problems([("legend", "यहाँ एक राक्षस रहता था [1]।")], 1, 2, "hi")
    assert any("legend not told as legend" in p for p in found)


def test_hindi_is_told_from_the_given_outline() -> None:
    from guide.katha.facts import Subject
    from guide.katha.pipeline import plan, write

    subject = Subject(kind="place", name="Devaraja Market", city="Mysuru", poi_ids=[1])
    facts = long_facts()
    outline = asyncio.run(plan(FakeKathaModel(), subject, 2, facts))
    prompts = []

    class Recording(FakeKathaModel):
        async def json(self, *a, **k):
            raise AssertionError("a given outline is never re-planned")

        async def text(self, prompt, *a, **k):
            prompts.append(prompt)
            return await super().text(prompt, *a, **k)

    story, notes = asyncio.run(write(Recording(), subject, 2, facts, lang="hi", outline=outline))
    assert story.lang == "hi" and notes["outline"] == outline.model_dump()
    assert all("Language: write in Hindi" in p for p in prompts[:2])  # draft and critique
    assert "Write in Hindi" not in outline_prompt_text(subject, facts)
    with pytest.raises(KathaFailed, match="no Katha voice"):
        asyncio.run(write(Recording(), subject, 2, facts, lang="xx", outline=outline))


def outline_prompt_text(subject, facts) -> str:
    from guide.katha.pipeline import outline_prompt

    return outline_prompt(subject, 2, facts)


class CacheDB:
    """katha_cache in a dict; resolve and gather are patched out."""

    def __init__(self) -> None:
        self.rows: dict[str, tuple[dict, dict]] = {}

    def execute(self, sql, params):
        db = self

        class Result:
            def fetchone(self):
                return db.rows.get(params[0]) if sql.startswith("SELECT") else None

        if sql.startswith("INSERT"):
            self.rows.setdefault(params[0], (json.loads(params[1]), json.loads(params[2])))
        return Result()


def test_katha_hindi_reuses_the_english_outline_and_caches_both(monkeypatch) -> None:
    import sys

    k = sys.modules["guide.katha"]  # the package; guide.katha the attribute is the function
    from guide.katha.facts import Subject

    subject = Subject(kind="place", name="Devaraja Market", city="Mysuru", poi_ids=[1])
    monkeypatch.setattr(k, "resolve", lambda *a: subject)
    monkeypatch.setattr(k, "gather", lambda *a: long_facts())
    db, model = CacheDB(), LongWinded()
    hi = asyncio.run(katha(KathaRequest(subject_kind="place", subject="x", length_min=2, lang="hi"), db, model))
    assert hi.lang == "hi" and model.labels.count("katha outline") == 1  # one outline, two tellings
    assert len(db.rows) == 2
    (en_story, en_notes), (hi_story, hi_notes) = db.rows.values()
    assert en_story["lang"] == "en" and hi_notes["outline"] == en_notes["outline"]
    assert hi_notes["key_inputs"][-1] == "hi" and len(en_notes["key_inputs"]) == 5
    # a language Katha has no voice for gets the English story, for translate to carry
    ta = asyncio.run(katha(KathaRequest(subject_kind="place", subject="x", length_min=2, lang="ta"), db, model))
    assert ta.lang == "en" and model.labels.count("katha outline") == 1 and len(db.rows) == 2


def test_lang_sample_facts_come_from_the_seed_in_story_order() -> None:
    from guide.katha.facts import CAP
    from guide.scripts.katha_lang_sample import facts_for

    subject, facts = facts_for("Mysore Palace", 2)
    assert subject.city == "Mysuru" and 2 <= len(facts) <= CAP[2]
    assert [f.n for f in facts] == list(range(1, len(facts) + 1))
    assert not any("ticket" in (f.title or "").lower() for f in facts)  # practical rows left out


def test_a_bracketed_year_range_is_prose_not_a_citation() -> None:
    assert checks.citations("Built between [1990-1995] by the city [2].") == [2]
    assert checks.problems([("history", " ".join(["word"] * 250) + " in [1897] [1].")], 1, 2) == []


def test_chat_to_the_user_is_not_story() -> None:
    # Seen live in a 10-minute draft (TY6's pre-generation run, Oct 2026).
    text = ("[HISTORY]\nThe palace burned in 1897 [1].\n\n"
            "Would you like a summary of the next segment of the city's history?\n\n"
            "[HISTORY]\nHere's the strange part: Irwin drew a new plan [2].\n\n"
            "Here is the rest of the story, told plainly.\n\nShall I continue with chapter 3?\n\n"
            "If you'd like a quiet corner, stand by the east gate [3].")  # fmt: skip
    assert parse(text) == [("history", "The palace burned in 1897 [1]."),
                           ("history", "Here's the strange part: Irwin drew a new plan [2]."),
                           ("history", "If you'd like a quiet corner, stand by the east gate [3].")]  # fmt: skip
    assert parse("[LEGEND]\nShould I stay, the queen asked [1].")[0][1].startswith("Should I stay")
    assert parse("[HISTORY]\nHerein lies the old gate [1].") == [("history", "Herein lies the old gate [1].")]


def test_pregenerate_logs_model_calls_at_info(monkeypatch) -> None:
    import logging

    from guide.scripts.katha_pregenerate import log_calls

    monkeypatch.delenv("TY_LOG_LEVEL", raising=False)
    log_calls()
    assert logging.getLogger("guide.katha").isEnabledFor(logging.INFO)
    assert logging.getLogger("core.llm").isEnabledFor(logging.INFO)


# --- Kannada, like Hindi (rule 12) ---


@pytest.mark.parametrize("phrase", checks.BANNED_LANG["kn"])
def test_every_kannada_banned_phrase_is_caught(phrase) -> None:
    assert phrase in checks.slop(f"ಅರಮನೆ {phrase} ಕಲ್ಲಿನ ಗಂಟೆ ಇದೆ.", "kn")


def test_kannada_cues_counts_and_band() -> None:
    assert checks.legend_told("ಜನ ಹೇಳುತ್ತಾರೆ, ಇಲ್ಲಿ ಒಬ್ಬ ರಾಕ್ಷಸ ಇದ್ದ [1].", "kn")
    assert checks.legend_told("ತಲಕಾಡಿನ ಶಾಪದ ಪ್ರತೀತಿ ಇದೆ.", "kn")
    assert not checks.legend_told("ಇಲ್ಲಿ ಒಬ್ಬ ರಾಕ್ಷಸ ಇದ್ದ [1].", "kn")
    assert checks.words("ಮೈಸೂರು ಅರಮನೆಯನ್ನು 1912ರಲ್ಲಿ ಕಟ್ಟಲಾಯಿತು [1, 2].", "kn") == 4
    assert checks.band(2, "kn") == (132, 240) and checks.band(2, "hi") == (242, 440)
    assert checks.band(2) == checks.BANDS[2]
    assert checks.slop("ಅರಮನೆಯ ಮುಂದೆ ಮಲ್ಲಿಗೆ ಮಾರುವವರು ಕುಳಿತಿದ್ದಾರೆ.", "kn") == []


def test_kannada_is_told_from_the_same_outline_through_katha(monkeypatch) -> None:
    import sys

    from guide.katha.facts import Subject

    k = sys.modules["guide.katha"]
    subject = Subject(kind="place", name="Devaraja Market", city="Mysuru", poi_ids=[1])
    monkeypatch.setattr(k, "resolve", lambda *a: subject)
    monkeypatch.setattr(k, "gather", lambda *a: long_facts())
    db, model = CacheDB(), LongWinded()
    req = KathaRequest(subject_kind="place", subject="x", length_min=2, lang="kn")
    kn = asyncio.run(katha(req, db, model))
    assert kn.lang == "kn" and model.labels.count("katha outline") == 1
    en_notes, kn_notes = (n for _, n in db.rows.values())
    assert kn_notes["outline"] == en_notes["outline"] and kn_notes["key_inputs"][-1] == "kn"
    low, high = checks.band(2, "kn")
    assert low <= checks.words(kn.text, "kn") <= high


# --- HQ QA: history first, every paragraph cited, nothing told twice, every source linked ---


def test_a_legend_never_opens_a_story_that_has_history() -> None:
    long = " ".join(f"w{i}" for i in range(260))
    legend_first = [("legend", "People here say a queen cursed the kings [1]."), ("history", f"{long} [2].")]
    assert "opens with a legend; lead with history when there is history" in checks.problems(legend_first, 2, 2)
    history_first = list(reversed(legend_first))
    assert not any("opens with" in p for p in checks.problems(history_first, 2, 2))
    only_legend = [("legend", f"People here say {long} [1].")]
    assert not any("opens with" in p for p in checks.problems(only_legend, 1, 2))


def test_every_paragraph_cites_legends_too() -> None:
    long = " ".join(f"w{i}" for i in range(260))
    found = checks.problems([("history", f"{long} [1]."), ("legend", "People here say it sang.")], 1, 2)
    assert any("uncited legend segment" in p for p in found)


def test_a_fact_told_twice_is_caught_in_a_real_story() -> None:
    # Mysuru 5 min, taste-gate pack (Oct 2026): the curse told in two places.
    story = json.loads((TASTE_GATE / "key" / "mysuru-5min" / "katha.json").read_text(encoding="utf-8"))
    pairs = checks.repeats(story["text"])
    assert pairs and pairs[0][0].startswith("The story goes that in 1610")
    echo = "The bird over the gate still looks at the hill. Look up once more at that bird on the gate."
    assert checks.repeats(echo) == []  # an image returned in new words is not a repeat


def test_unlinked_facts_stay_and_are_named_honestly() -> None:
    from guide.katha import facts as f

    seen = []

    class Recording:
        def execute(self, sql, params):
            seen.append(sql)

            class R:
                def fetchall(self):
                    return []

            return R()

    f.gather(Recording(), f.Subject(kind="city", name="Mysuru", city="Mysuru"), 2)
    assert seen and not any("source_url, '') <>" in sql for sql in seen)  # nothing dropped

    def src(url, name):
        return Fact(n=1, chunk_id=1, city="Mysuru", title="Three palaces burned", body="B.",
                    is_legend=False, source_name=name, source_url=url).source  # fmt: skip

    assert src("https://example.org/a", "Wikipedia") == "https://example.org/a"  # web: its link
    assert src(None, "travel-yantra field notes") == "Travel Yantra field notes"
    assert src(None, "Mysore Palace Board") == "Mysore Palace Board"  # original name, no link
    assert src(None, None) == "Travel Yantra field notes"

