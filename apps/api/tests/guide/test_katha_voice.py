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

    def put(self, name, data, content_type):
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
    assert v.attach(s, fetch=lambda url: None) == []

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
