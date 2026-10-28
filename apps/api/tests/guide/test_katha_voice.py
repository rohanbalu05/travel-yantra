"""Katha read aloud: voice choice, chapter inputs, budget, storage and the API's attach.
Fakes only: no TTS, no Storage, no network."""

import base64
import json

import pytest

from guide.katha import voice as v
from ty_contracts import KathaStory, StorySegment

LIST = ["hi-IN-Chirp3-HD-Achird", "hi-IN-Chirp3-HD-Charon", "hi-IN-Neural2-A", "hi-IN-Wavenet-A"]


def story(lang="en", length=2, paras=3, words=40) -> KathaStory:
    body = " ".join(["word"] * words)
    segs = [StorySegment(label="history", text=f"{body} {i} [{i + 1}].") for i in range(paras)]
    return KathaStory(subject_kind="place", subject="Mysore Palace", length_min=length,
                      text="\n\n".join(s.text for s in segs), segments=segs, lang=lang)  # fmt: skip


class FakeHttp:
    """TTS synthesize returns the input back as 'audio'; voices lists LIST."""

    def __init__(self):
        self.calls = []

    def __call__(self, method, url, body, data, headers):
        self.calls.append((method, url, body))
        if "/voices" in url:
            return 200, json.dumps({"voices": [{"name": n, "languageCodes": ["hi-IN"]} for n in LIST]}).encode()
        text = next(iter(body["input"].values()))
        return 200, json.dumps({"audioContent": base64.b64encode(text.encode()).decode()}).encode()

    def synth(self):
        return [b for _, u, b in self.calls if u.endswith("text:synthesize")]


class MemoryStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def get(self, name):
        return self.objects.get(name)

    def exists(self, name):
        return f"https://example.org/bucket/{name}" if name in self.objects else None

    def put(self, name, data, content_type):
        assert name not in self.objects, "objectCreator cannot overwrite"
        self.objects[name] = data
        return f"https://example.org/bucket/{name}"


def test_voice_choice_prefers_chirp3_and_falls_back():
    assert v.voices(FakeHttp(), "hi") == sorted(LIST)
    assert v.pick_voice(LIST) == "hi-IN-Chirp3-HD-Charon"
    assert v.pick_voice(["kn-IN-Wavenet-B", "kn-IN-Standard-A"]) == "kn-IN-Wavenet-B"
    assert v.pick_voice(["bn-IN-Chirp3-HD-Zephyr"]) == "bn-IN-Chirp3-HD-Zephyr"
    assert v.pick_voice([]) is None


def test_citations_are_never_read_out():
    assert v.speakable("Built in 1912 [1][2], by Irwin [3] .") == "Built in 1912, by Irwin."
    assert v.speakable("मैसूर का महल [1, 2] ।") == "मैसूर का महल।"


def test_chapters_follow_the_pipeline_or_split_evenly():
    ten = story(length=10, paras=8)
    assert [len(c) for c in v.chapters(ten)] == [2, 2, 2, 2]
    assert [len(c) for c in v.chapters(ten, starts=[0, 3, 5, 7])] == [3, 2, 2, 1]
    assert len(v.chapters(story(length=2))) == 1


def test_requests_stay_under_the_byte_limit_with_pauses():
    hindi = ["मैसूर का महल बहुत पुराना है। " * 60] * 3  # ~1,700 chars, ~4,700 bytes each
    inputs = v.requests_for(hindi, chirp=True, last=False)
    assert len(inputs) >= 3 and all(len(i["markup"].encode()) <= v.MAX_BYTES for i in inputs)
    assert inputs[-1]["markup"].endswith("[pause long]")
    short = v.requests_for(["One.", "Two & three."], chirp=False, last=True)
    assert short == [{"ssml": '<speak>One.<break time="700ms"/>Two &amp; three.</speak>'}]


def test_read_aloud_counts_stores_and_reads_once():
    http, store, budget = FakeHttp(), MemoryStorage(), v.Budget(100_000)
    s = story(length=10, paras=8, words=30)
    audio, sent = v.read_aloud(s, "en-IN-Chirp3-HD-Charon", http, store, budget)
    assert [a.chapter for a in audio] == [1, 2, 3, 4] and sent == budget.used > 0
    assert sum(a.characters for a in audio) == sent
    where = v.prefix(s)
    assert set(store.objects) == {f"{where}/ch{n}.mp3" for n in range(1, 5)} | {f"{where}/audio.json"}
    assert b"[pause long]" in store.objects[f"{where}/ch1.mp3"] and b"[1]" not in store.objects[f"{where}/ch1.mp3"]
    calls = len(http.synth())
    again, sent2 = v.read_aloud(s, "en-IN-Chirp3-HD-Charon", http, store, budget)
    assert again == audio and sent2 == 0 and len(http.synth()) == calls  # cached by story key


def test_the_budget_stops_before_the_call():
    http, store = FakeHttp(), MemoryStorage()
    with pytest.raises(v.BudgetSpent):
        v.read_aloud(story(paras=3, words=200), "en-IN-Chirp3-HD-Charon", http, store, v.Budget(50))
    assert http.synth() == [] and store.objects == {}


def test_a_new_text_or_language_gets_new_audio():
    a, b = story(), story(words=41)
    assert v.audio_key(a) != v.audio_key(b) and v.audio_key(a) != v.audio_key(story(lang="hi"))
    assert v.audio_key(a) == v.audio_key(story())


def test_attach_reads_the_manifest_and_never_fails(monkeypatch):
    s = story()
    monkeypatch.delenv("KATHA_AUDIO_BASE_URL", raising=False)
    assert v.attach(s, fetch=lambda url: pytest.fail("no base url, no fetch")) == []
    monkeypatch.setenv("KATHA_AUDIO_BASE_URL", "https://example.org/bucket/")
    manifest = [{"chapter": 1, "url": "https://example.org/bucket/x.mp3", "voice": "en-IN-Chirp3-HD-Charon",
                 "characters": 120}]  # fmt: skip
    seen = []
    got = v.attach(s, fetch=lambda url: seen.append(url) or json.dumps(manifest).encode())
    assert seen == [f"https://example.org/bucket/{v.prefix(s)}/audio.json"] and got[0].characters == 120
    v._seen.clear()
    assert v.attach(s, fetch=lambda url: None) == []
    v._seen.clear()

    def broken(url):
        raise OSError("sample: network down")

    assert v.attach(s, fetch=broken) == []


def test_chapter_starts_follow_the_chapters_and_survive_a_trim():
    from guide.katha.pipeline import chapter_starts

    assert chapter_starts([3, 2, 2, 1], 8) == [0, 3, 5, 7]
    assert chapter_starts([4, 4], 6) == [0, 3]  # a trim cut two paragraphs
    assert chapter_starts([5], 5) == [0] and chapter_starts([], 0) == [0]


def test_the_pipeline_records_chapter_starts() -> None:
    import asyncio

    from guide.katha.facts import Fact, Subject
    from guide.katha.fake import FakeKathaModel
    from guide.katha.pipeline import write

    facts = [Fact(n=i, chunk_id=i, city="Mysuru", title=f"T{i}", body=f"Sample fact {i} about the palace.",
                  is_legend=False, source_name="S", source_url=f"https://s/{i}") for i in range(1, 14)]  # fmt: skip
    subject = Subject(kind="place", name="Mysore Palace", city="Mysuru", poi_ids=[1])
    story, notes = asyncio.run(write(FakeKathaModel(), subject, 5, facts))
    starts = notes["chapter_starts"]
    assert starts[0] == 0 and len(starts) == 2 and starts[1] < len(story.segments)


def test_the_endpoint_attaches_stored_audio(monkeypatch):
    import asyncio
    import sys

    import guide
    from ty_contracts import KathaRequest

    s = story()
    pkg = sys.modules["guide"]

    async def cached(req, db, model):
        return s

    monkeypatch.setattr(pkg, "katha", cached)
    monkeypatch.setenv("KATHA_AUDIO_BASE_URL", "https://example.org/bucket")
    manifest = json.dumps([{"chapter": 1, "url": "https://example.org/bucket/ch1.mp3",
                            "voice": "en-IN-Chirp3-HD-Charon", "characters": 99}]).encode()  # fmt: skip
    monkeypatch.setattr(v, "_fetch", lambda url: manifest)
    req = KathaRequest(subject_kind="place", subject="Mysore Palace", length_min=2)
    out = asyncio.run(guide.post_katha(req, db=None, model=None))
    assert [a.url for a in out.audio] == ["https://example.org/bucket/ch1.mp3"] and out.text == s.text
    v._seen.clear()
    monkeypatch.setattr(v, "_fetch", lambda url: None)  # not read aloud yet
    assert asyncio.run(guide.post_katha(req, db=None, model=None)).audio == []


def test_the_voice_report_lists_every_language_and_the_choice(tmp_path, monkeypatch):
    from guide.scripts import katha_voice as script

    monkeypatch.setattr(script, "OUT", tmp_path)
    report = script.voice_report(FakeHttp())
    assert set(report) == set(v.LANG_CODE)
    assert report["hi"]["chosen"] == "hi-IN-Chirp3-HD-Charon"
    assert json.loads((tmp_path / "voices.json").read_text(encoding="utf-8")) == report
    assert set(script.DEMO) >= {"place:Mysore Palace:2:hi"} and len(script.DEMO) == 5


def test_a_freshly_enabled_api_is_retried_and_billed_once(monkeypatch):
    monkeypatch.setattr(v.time, "sleep", lambda s: None)
    real = FakeHttp()
    flaky = {"left": 2}

    def http(method, url, body, data, headers):
        if flaky["left"]:
            flaky["left"] -= 1
            return 403, b'{"error": {"message": "Cloud Text-to-Speech API has not been used in project"}}'
        return real(method, url, body, data, headers)

    budget = v.Budget(1000)
    mp3 = v.synthesize(http, [{"markup": "One line."}], "en-IN-Chirp3-HD-Charon", "en", budget)
    assert mp3 == b"One line." and budget.used == len("One line.")
    status, _ = v._with_retry(lambda *a: (403, b"denied: no permission"), "GET", "u", None, None, {})
    assert status == 403  # a real permission error is not retried


@pytest.fixture(autouse=True)
def fresh_manifest_cache(monkeypatch):
    monkeypatch.setattr(v, "_seen", {})


def test_a_run_that_died_resumes_without_reading_stored_chapters_again():
    http, store = FakeHttp(), MemoryStorage()
    s = story(length=5, paras=4, words=30)
    groups = v.chapters(s)
    first = v.characters(v.requests_for(groups[0], True, last=False))
    with pytest.raises(v.BudgetSpent):  # enough for chapter 1, not chapter 2
        v.read_aloud(s, "en-IN-Chirp3-HD-Charon", http, store, v.Budget(first + 5))
    assert set(store.objects) == {f"{v.prefix(s)}/ch1.mp3"}
    calls = len(http.synth())
    audio, sent = v.read_aloud(s, "en-IN-Chirp3-HD-Charon", http, store, v.Budget(100_000))
    assert [a.chapter for a in audio] == [1, 2] and audio[0].characters == first
    assert sent == audio[1].characters  # only chapter 2 was read and billed
    assert len(http.synth()) == calls + 1 and f"{v.prefix(s)}/audio.json" in store.objects


def test_an_endless_sentence_is_cut_at_spaces_under_the_limit():
    endless = " ".join(["मैसूर"] * 1200)  # ~19,000 bytes, no full stop
    inputs = v.requests_for([endless], chirp=True, last=True)
    assert len(inputs) >= 4 and all(len(i["markup"].encode()) <= v.MAX_BYTES for i in inputs)
    escaped = v.requests_for(["a & b " * 900], chirp=False, last=True)  # grows when escaped
    assert all(len(i["ssml"].encode()) <= v.MAX_BYTES for i in escaped)


def test_manifest_lookups_are_remembered():
    import os

    os.environ["KATHA_AUDIO_BASE_URL"] = "https://example.org/bucket"
    try:
        seen = []
        manifest = json.dumps([{"chapter": 1, "url": "u", "voice": "x", "characters": 1}]).encode()
        s = story()
        assert v.attach(s, fetch=lambda u: seen.append(u) or manifest)
        assert v.attach(s, fetch=lambda u: seen.append(u) or manifest)
        assert len(seen) == 1
    finally:
        del os.environ["KATHA_AUDIO_BASE_URL"]


def test_a_story_the_api_cannot_give_is_skipped_and_the_run_goes_on(tmp_path, monkeypatch):
    # TY6's run: Mysuru 5 min hi answered 503 (failed its checks twice) and the run died.
    import urllib.error

    from guide.scripts import katha_voice as script

    monkeypatch.setattr(script, "OUT", tmp_path)

    def fetch(kind, subject, length, lang):
        if lang == "hi":
            raise urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None)
        return story(lang=lang)

    report = {lang: {"chosen": f"{lang}-IN-Chirp3-HD-Charon"} for lang in v.LANG_CODE}
    store = MemoryStorage()
    skipped = script.run(["city:Mysuru:5:hi", "city:Mysuru:2:en"], fetch, report, FakeHttp(), store,
                         v.Budget(100_000))  # fmt: skip
    assert skipped == 1 and any(k.endswith("/en/ch1.mp3") for k in store.objects)


# --- HQ P7: audio on demand, a chapter a request, under a daily cap ---


class JobDB:
    """katha_audio_job and katha_tts_usage in memory, for the statements ondemand runs."""

    def __init__(self, used: int = 0):
        self.jobs: dict[str, bool] = {}  # key -> claimed
        self.used = used

    def execute(self, sql, params=()):
        row = None
        if sql.startswith("INSERT INTO katha_audio_job"):
            if params[0] not in self.jobs:
                self.jobs[params[0]], row = False, (1,)
        elif sql.startswith("UPDATE katha_audio_job SET claimed_until = now()"):
            if self.jobs.get(params[1]) is False:
                self.jobs[params[1]], row = True, (1,)
        elif sql.startswith("UPDATE katha_audio_job SET claimed_until = NULL"):
            self.jobs[params[0]] = False
        elif sql.startswith("INSERT INTO katha_tts_usage"):
            n, cap = params
            if self.used + n <= cap:
                self.used += n
                row = (self.used,)

        class R:
            def fetchone(self):
                return row

        return R()


@pytest.fixture
def on_demand(monkeypatch):
    from guide.katha import ondemand

    monkeypatch.setenv("KATHA_AUDIO_BUCKET", "sample-bucket")
    monkeypatch.setenv("KATHA_AUDIO_BASE_URL", "https://example.org/bucket")
    monkeypatch.setenv("KATHA_TTS_DAILY_CHARS", "30000")
    monkeypatch.setattr(ondemand, "chosen_voices", lambda: {"en": "en-IN-Chirp3-HD-Charon"})
    return ondemand


def test_audio_on_demand_reads_a_chapter_a_request_then_is_ready(on_demand):
    db, http, store = JobDB(), FakeHttp(), MemoryStorage()
    s = story(length=5, paras=4, words=30)  # two chapters
    steps = [on_demand.advance(s, db, http=http, storage=store) for _ in range(3)]
    assert [st for _, st in steps] == ["pending", "pending", "ready"]  # filed, chapter 1, chapter 2
    assert [a.chapter for a in steps[2][0]] == [1, 2] and db.used == sum(a.characters for a in steps[2][0])
    assert f"{v.prefix(s)}/audio.json" in store.objects


def test_audio_on_demand_holds_the_daily_cap_and_fails_soft(on_demand, monkeypatch):
    db = JobDB(used=29_990)  # today nearly spent
    s = story(length=2)
    assert on_demand.advance(s, db, http=FakeHttp(), storage=MemoryStorage())[1] == "pending"
    assert on_demand.advance(s, db, http=FakeHttp(), storage=MemoryStorage()) == ([], "none")
    assert db.used == 29_990  # nothing sent past the cap
    monkeypatch.setenv("KATHA_TTS_DAILY_CHARS", "0")
    assert on_demand.advance(story(length=2, paras=1), JobDB(), http=FakeHttp(), storage=MemoryStorage())[1] == "none"


def test_a_claimed_story_is_not_read_twice(on_demand):
    db, s = JobDB(), story(length=2)
    on_demand.advance(s, db, http=FakeHttp(), storage=MemoryStorage())
    db.jobs[v.audio_key(s)] = True  # another instance is reading it now
    http = FakeHttp()
    assert on_demand.advance(s, db, http=http, storage=MemoryStorage()) == ([], "pending") and not http.synth()


def test_the_endpoint_says_pending_then_ready(monkeypatch, on_demand):
    import asyncio
    import sys

    import guide
    from ty_contracts import KathaRequest

    s = story(length=2)
    pkg = sys.modules["guide"]

    async def cached(req, db, model):
        return s

    monkeypatch.setattr(pkg, "katha", cached)
    monkeypatch.setattr(v, "_fetch", lambda url: None)
    db, store, http = JobDB(), MemoryStorage(), FakeHttp()
    monkeypatch.setattr(v, "adc_http", lambda: http)
    monkeypatch.setattr(on_demand, "_storage", lambda h: store)
    v._seen.clear()
    req = KathaRequest(subject_kind="place", subject="Mysore Palace", length_min=2)
    first = asyncio.run(guide.post_katha(req, db=db, model=None))
    assert first.audio_status == "pending" and first.audio == [] and first.text == s.text
    second = asyncio.run(guide.post_katha(req, db=db, model=None))
    assert second.audio_status == "ready" and [a.chapter for a in second.audio] == [1]
    v._seen.clear()


def test_ten_minute_stories_are_404_until_they_pass():
    import asyncio

    from fastapi import HTTPException

    import guide
    from ty_contracts import KathaRequest

    with pytest.raises(HTTPException) as e:
        asyncio.run(guide.post_katha(KathaRequest(subject_kind="place", subject="Mysore Palace", length_min=10),
                                     db=None, model=None))  # fmt: skip
    assert e.value.status_code == 404 and "5-minute" in e.value.detail


def test_cached_stories_name_our_notes_as_field_notes():
    from guide.katha import labelled

    s = story().model_copy(update={"sources": ["https://example.org/a", "travel-yantra field notes", ""]})
    assert labelled(s).sources == ["https://example.org/a", "Travel Yantra field notes", "Travel Yantra field notes"]


def test_the_library_lists_ready_subjects_with_lengths_langs_and_audio():
    from guide.katha import library as lib

    def row(kind, subject, length, lang, city=None, pop=None):
        st = story(lang=lang, length=length).model_copy(update={"subject_kind": kind, "subject": subject})
        return (st.model_dump(mode="json"), city, pop)

    rows = [row("place", "Mysore Palace", 2, "en", "Mysuru", 5), row("place", "Mysore Palace", 5, "hi", "Mysuru", 5),
            row("city", "Mysuru", 2, "en"), row("place", "Devaraja Market", 2, "en", "Mysuru", 3),
            row("place", "Mysore Palace", 10, "en", "Mysuru", 5)]  # fmt: skip

    class DB:
        def execute(self, sql, params):
            assert params == ("8",) or params[0].isdigit()

            class R:
                def fetchall(self):
                    return rows

            return R()

    lib._memo.clear()
    out = lib.library(DB(), attach=lambda s: [1] if s.lang == "hi" else [])
    assert out == [
        {"subject_kind": "city", "subject": "Mysuru", "city": "Mysuru", "lengths": [2], "langs": ["en"],
         "has_audio": False},
        {"subject_kind": "place", "subject": "Mysore Palace", "city": "Mysuru", "lengths": [2, 5],
         "langs": ["en", "hi"], "has_audio": True},
        {"subject_kind": "place", "subject": "Devaraja Market", "city": "Mysuru", "lengths": [2], "langs": ["en"],
         "has_audio": False},
    ]  # fmt: skip
    lib._memo.clear()
