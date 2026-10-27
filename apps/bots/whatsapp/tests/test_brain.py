import json
from datetime import date

import httpx
import pytest
from ty_contracts import Lang

from app import brain as brain_mod
from app.brain import HELP, MAX_REPLY, SAMPLE, Brain, detect_lang, parse_trip

TODAY = date(2026, 10, 27)
ITINERARY = json.loads(SAMPLE.read_text(encoding="utf-8"))["itinerary"]


@pytest.mark.parametrize(
    "text, origin, dest, start, end",
    [
        ("Plan Bengaluru to Goa, 11-14 Dec", "Bengaluru", "Goa", (2026, 12, 11), (2026, 12, 14)),
        ("from mysuru to ooty 3 to 5 nov", "Mysuru", "Ooty", (2026, 11, 3), (2026, 11, 5)),
        (
            "Mujhe Bengaluru se Goa jaana hai 11 Dec se 14 Dec tak",
            "Bengaluru",
            "Goa",
            (2026, 12, 11),
            (2026, 12, 14),
        ),
        (
            "Chennai to Pondicherry 30 dec - 2 jan",
            "Chennai",
            "Pondicherry",
            (2026, 12, 30),
            (2027, 1, 2),
        ),
        ("Pune to Goa 5-8 March", "Pune", "Goa", (2027, 3, 5), (2027, 3, 8)),
    ],
)
def test_parse_trip(text, origin, dest, start, end):
    trip = parse_trip(text, TODAY)
    assert trip is not None
    assert (trip.origin, trip.destinations) == (origin, [dest])
    assert (trip.start_date, trip.end_date) == (date(*start), date(*end))


@pytest.mark.parametrize(
    "text",
    ["What should we eat in Goa?", "Bengaluru to Goa", "11-14 Dec", "Goa to Pune 31-32 Dec"],
)
def test_not_a_trip(text):
    assert parse_trip(text, TODAY) is None


@pytest.mark.parametrize(
    "text, lang",
    [
        ("Goa jaana hai", Lang.en),
        ("गोवा में क्या खाएं?", Lang.hi),
        ("ಮೈಸೂರು ಅರಮನೆ ಯಾವಾಗ ತೆರೆಯುತ್ತದೆ?", Lang.kn),
        ("மதுரை கோயில்", Lang.ta),
        ("హైదరాబాద్ బిర్యానీ", Lang.te),
        ("কলকাতায় কী খাব?", Lang.bn),
    ],
)
def test_detect_lang(text, lang):
    assert detect_lang(text) == lang


async def test_greeting_gets_help():
    assert await Brain(base="").reply("Hi") == HELP


def _fake_api(monkeypatch, handler):
    seen = []

    def record(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    real = httpx.AsyncClient
    monkeypatch.setattr(
        brain_mod.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(record), **kw),
    )
    return seen


async def test_trip_calls_api_plan(monkeypatch):
    done = {"stage": "done", "message": "done", "partial": ITINERARY}
    sse = "data: " + json.dumps({"stage": "planning", "message": "p"}) + "\n\n"
    sse += "data: " + json.dumps(done) + "\n\n"
    seen = _fake_api(monkeypatch, lambda req: httpx.Response(200, text=sse))
    reply = await Brain(base="http://api.test", today=TODAY).reply("Bengaluru to Goa 11-14 Dec")
    assert seen[0].url.path == "/plan"
    sent = json.loads(seen[0].content)
    assert (sent["origin"], sent["destinations"], sent["start_date"]) == (
        "Bengaluru",
        ["Goa"],
        "2026-12-11",
    )
    assert "Day 1" in reply and "offline" not in reply


async def test_question_calls_guide_ask_in_users_language(monkeypatch):
    answer = {"text": "उत्तर", "citations": [{"title": "Sample source", "url": None}], "lang": "hi"}
    seen = _fake_api(monkeypatch, lambda req: httpx.Response(200, json=answer))
    reply = await Brain(base="http://api.test").reply("गोवा में क्या खाएं?")
    assert seen[0].url.path == "/guide/ask"
    assert json.loads(seen[0].content)["lang"] == "hi"
    assert reply.startswith("उत्तर") and "Sample source" in reply


async def test_long_answers_are_capped(monkeypatch):
    answer = {"text": "x" * 5000, "lang": "en"}
    _fake_api(monkeypatch, lambda req: httpx.Response(200, json=answer))
    reply = await Brain(base="http://api.test").reply("Tell me everything about Hampi")
    assert len(reply) == MAX_REPLY


async def test_plan_error_event_raises(monkeypatch):
    sse = "data: " + json.dumps({"stage": "error", "message": "no route"}) + "\n\n"
    _fake_api(monkeypatch, lambda req: httpx.Response(200, text=sse))
    with pytest.raises(RuntimeError, match="no route"):
        await Brain(base="http://api.test", today=TODAY).reply("Bengaluru to Goa 11-14 Dec")
