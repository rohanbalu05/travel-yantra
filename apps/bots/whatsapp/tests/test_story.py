import json

import httpx
import pytest
from test_brain import TRANSLATE, fake_http, tagging_translate, text
from ty_contracts import Lang

from app.brain import NO_STORY, STORY_BUSY, Brain, parse_story
from app.translate import Translator

API = "http://api.test"


@pytest.mark.parametrize(
    "msg, parsed",
    [
        ("story Mysore Palace", ("Mysore Palace", 2, None)),
        ("Story of Hampi 5 min", ("Hampi", 5, None)),
        ("katha Mysore Palace in Hindi", ("Mysore Palace", 2, Lang.hi)),
        (
            "tell me the story of Vittala Temple 10 minutes in kannada.",
            ("Vittala Temple", 10, Lang.kn),
        ),
        ("kahani Gol Gumbaz hindi", ("Gol Gumbaz", 2, Lang.hi)),
        ("कथा मैसूर पैलेस", ("मैसूर पैलेस", 2, None)),
        ("मैसूर पैलेस की कहानी", ("मैसूर पैलेस", 2, None)),
        ("कहानी Mysore Palace हिंदी में", ("Mysore Palace", 2, Lang.hi)),
        ("what is the story behind the name?", None),
        ("Plan Bengaluru to Goa", None),
        ("story", None),
    ],
)
def test_parse_story(msg, parsed):
    assert parse_story(msg) == parsed


def story(lang="en", audio=(), sources=("https://w.example/mysore-palace",)) -> dict:
    return {
        "subject_kind": "place",
        "subject": "Mysore Palace",
        "length_min": 2,
        "text": "हर दशहरे पर महल जगमगाता है। [1]"
        if lang == "hi"
        else "Every Dasara the palace glows. [1]",
        "sources": list(sources),
        "lang": lang,
        "audio": [
            {"chapter": n, "url": f"https://audio.example/{n}.mp3", "voice": "v", "characters": 10}
            for n in audio
        ],
    }


def katha_api(*answers):
    """Fake API answering successive /guide/katha calls; also a tagging translate service."""
    answers = list(answers)

    def handler(req):
        if req.url.host == "translate.test":
            return tagging_translate(req)
        status, body = answers.pop(0)
        return httpx.Response(status, json=body)

    return handler


async def test_hindi_story_is_written_natively_with_its_audio(monkeypatch):
    seen = fake_http(monkeypatch, katha_api((200, story("hi", audio=(2, 1)))))
    audio, notes = [], []

    async def notify(t):
        notes.append(t)

    brain = Brain(base=API, translator=Translator(base=TRANSLATE))
    reply = await brain.handle(text("katha Mysore Palace in Hindi"), notify=notify, audio=audio)
    [req] = [r for r in seen if r.url.host == "api.test"]
    # The story itself is not translated: only the "working on it" note went to translate.
    assert [r.url.host for r in seen].count("translate.test") == 1
    assert req.url.path == "/guide/katha"
    assert json.loads(req.content) == {
        "subject_kind": "place",
        "subject": "Mysore Palace",
        "length_min": 2,
        "lang": "hi",
        "places": [],
    }
    assert reply == "हर दशहरे पर महल जगमगाता है। [1]\n\n[1] https://w.example/mysore-palace"
    assert audio == ["https://audio.example/1.mp3", "https://audio.example/2.mp3"]
    assert len(notes) == 1 and notes[0].startswith("<hi>")  # "working on it", in Hindi
    assert brain.users["15550001111"].lang == Lang.hi


async def test_devanagari_request_asks_for_hindi(monkeypatch):
    seen = fake_http(monkeypatch, katha_api((200, story("hi"))))
    await Brain(base=API).handle(text("मैसूर पैलेस की कहानी"))
    assert json.loads(seen[0].content)["lang"] == "hi"


async def test_english_story_for_a_tamil_user_is_translated_without_audio(monkeypatch):
    fake_http(monkeypatch, katha_api((200, story("en", audio=(1,)))))
    audio = []
    brain = Brain(base=API, translator=Translator(base=TRANSLATE))
    reply = await brain.handle(text("story Mysore Palace in Tamil"), audio=audio)
    assert reply.startswith("<ta>Every Dasara the palace glows. [1]")
    assert reply.endswith("[1] https://w.example/mysore-palace")
    assert audio == []  # English narration would not match a Tamil reply


async def test_english_story_with_audio(monkeypatch):
    fake_http(monkeypatch, katha_api((200, story("en", audio=(1,)))))
    audio = []
    reply = await Brain(base=API).handle(text("story Mysore Palace"), audio=audio)
    assert reply.startswith("Every Dasara") and audio == ["https://audio.example/1.mp3"]


async def test_unknown_place_is_tried_as_a_city(monkeypatch):
    city = {**story(), "subject_kind": "city", "subject": "Mysuru"}
    seen = fake_http(monkeypatch, katha_api((404, {"detail": "No story"}), (200, city)))
    await Brain(base=API).handle(text("story Mysuru"))
    assert [json.loads(r.content)["subject_kind"] for r in seen] == ["place", "city"]


async def test_no_story_anywhere(monkeypatch):
    fake_http(monkeypatch, katha_api((404, {}), (404, {})))
    reply = await Brain(base=API).handle(text("story Atlantis"))
    assert reply == NO_STORY.format(what="Atlantis")


async def test_story_busy(monkeypatch):
    seen = fake_http(monkeypatch, katha_api((503, {"detail": "busy"})))
    assert await Brain(base=API).handle(text("story Mysore Palace")) == STORY_BUSY
    assert len(seen) == 1  # a 503 is not retried as a city


async def test_offline_story_sends_no_audio():
    audio = []
    reply = await Brain(base="").handle(text("story Mysore Palace"), audio=audio)
    assert "Mysore Palace" in reply and audio == []


async def test_katha_errors_log_the_api_detail(monkeypatch, caplog):
    fake_http(monkeypatch, katha_api((404, {"detail": "No story for that place yet."}), (404, {})))
    await Brain(base=API).handle(text("story Atlantis"))
    assert "katha as place: HTTP 404 'No story for that place yet.'" in caplog.text
    assert "katha as city: HTTP 404 'HTTP 404'" in caplog.text
