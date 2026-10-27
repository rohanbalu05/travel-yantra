import json

import httpx
import pytest
from ty_contracts import Lang

from app import brain as brain_mod
from app import translate as translate_mod
from app.brain import ASKING, HELP, MAX_REPLY, SAMPLE, Brain, User, detect_lang, is_trip
from app.translate import Translator

ITINERARY = json.loads(SAMPLE.read_text(encoding="utf-8"))["itinerary"]
API = "http://api.test"
TRANSLATE = "http://translate.test"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def text(body: str, user: str = "15550001111") -> dict:
    return {"from": user, "id": "wamid.x", "type": "text", "text": {"body": body}}


def sse(*events: dict) -> str:
    return "".join(f": ping\n\ndata: {json.dumps(e)}\n\n" for e in events)


def done(itinerary=ITINERARY) -> dict:
    return {"stage": "done", "message": "done", "partial": itinerary, "plan_id": "p1"}


def fake_http(monkeypatch, handler):
    """One fake transport for every httpx client in the bot (API and translate)."""
    seen = []

    def record(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    real = httpx.AsyncClient
    fake = lambda **kw: real(transport=httpx.MockTransport(record), **kw)
    monkeypatch.setattr(brain_mod.httpx, "AsyncClient", fake)
    monkeypatch.setattr(translate_mod.httpx, "AsyncClient", fake)
    return seen


def tagging_translate(req: httpx.Request) -> httpx.Response:
    """Fake translate service: tags each text, keeps protected entities, flags nothing."""
    body = json.loads(req.content)
    outs = [f"<{body['target']}>{t}" for t in body["texts"]]
    return httpx.Response(
        200,
        json={"translations": outs, "target": body["target"], "via": [], "flags": [[] for _ in outs]},
    )


@pytest.mark.parametrize(
    "msg",
    [
        "Plan Bengaluru to Goa, 11-14 Dec",
        "Mujhe Bengaluru se Goa jaana hai 11 Dec se 14 Dec tak",
        "a weekend trip to Hampi",
        "Mysuru to Ooty 3 Nov",
        "मुझे गोवा की यात्रा करनी है",
        "ಮೈಸೂರು ಪ್ರವಾಸ ಯೋಜಿಸಿ",
        "மதுரை பயணம் திட்டமிடு",
        "హైదరాబాద్ ప్రయాణం",
        "দার্জিলিং ভ্রমণ",
    ],
)
def test_is_trip(msg):
    assert is_trip(msg)


@pytest.mark.parametrize(
    "msg",
    [
        "What should we eat in Goa?",
        "How do I get from Panaji to Old Goa?",
        "nearest hospital",
        "गोवा में शाकाहारी खाना कहाँ मिलेगा?",
    ],
)
def test_is_not_trip(msg):
    assert not is_trip(msg)


@pytest.mark.parametrize(
    "msg, lang",
    [
        ("Goa jaana hai", Lang.en),
        ("गोवा में क्या खाएं?", Lang.hi),
        ("ಮೈಸೂರು ಅರಮನೆ ಯಾವಾಗ ತೆರೆಯುತ್ತದೆ?", Lang.kn),
        ("மதுரை கோயில்", Lang.ta),
        ("హైదరాబాద్ బిర్యానీ", Lang.te),
        ("কলকাতায় কী খাব?", Lang.bn),
    ],
)
def test_detect_lang(msg, lang):
    assert detect_lang(msg) == lang


async def test_greeting_gets_help():
    assert await Brain(base="").handle(text("Hi")) == HELP


async def test_trip_sends_plantext_and_summarises(monkeypatch):
    seen = fake_http(monkeypatch, lambda req: httpx.Response(200, text=sse(done())))
    reply = await Brain(base=API).handle(text("Plan Bengaluru to Goa 11-14 Dec, 4 of us"))
    assert seen[0].url.path == "/plan"
    assert json.loads(seen[0].content) == {
        "text": "Plan Bengaluru to Goa 11-14 Dec, 4 of us",
        "lang": "en",
    }
    assert "Goa from Bengaluru" in reply and "Day 1" in reply and "offline" not in reply


async def test_needs_input_then_answers_are_resent_with_the_original(monkeypatch):
    replies = iter(
        [
            sse({"stage": "needs_input", "message": "q", "questions": ["Which dates?"]}),
            sse(done()),
        ]
    )
    seen = fake_http(monkeypatch, lambda req: httpx.Response(200, text=next(replies)))
    brain = Brain(base=API)
    first = await brain.handle(text("Plan a trip to Goa"))
    assert first == f"{ASKING}\n- Which dates?"
    second = await brain.handle(text("11-14 Dec"))
    assert json.loads(seen[1].content)["text"] == "Plan a trip to Goa\n11-14 Dec"
    assert "Day 1" in second


async def test_pending_questions_expire(monkeypatch):
    clock = Clock()
    seen = fake_http(
        monkeypatch,
        lambda req: httpx.Response(
            200, text=sse({"stage": "needs_input", "message": "q", "questions": ["When?"]})
        )
        if req.url.path == "/plan"
        else httpx.Response(200, json={"text": "Fish curry [1].", "citations": [{"title": "S"}]}),
    )
    brain = Brain(base=API, clock=clock)
    await brain.handle(text("Plan a trip to Goa"))
    clock.now += 31 * 60
    await brain.handle(text("What should we eat?"))
    assert seen[1].url.path == "/guide/ask"


async def test_cancel_clears_pending(monkeypatch):
    fake_http(
        monkeypatch,
        lambda req: httpx.Response(
            200, text=sse({"stage": "needs_input", "message": "q", "questions": ["When?"]})
        ),
    )
    brain = Brain(base=API)
    await brain.handle(text("Plan a trip to Goa"))
    assert await brain.handle(text("cancel")) == HELP
    assert brain.users["15550001111"].pending is None


async def test_question_goes_to_guide_with_numbered_sources(monkeypatch):
    answer = {
        "text": "Try fish curry [1] and bebinca [2].",
        "citations": [{"title": "Goan food", "url": "https://example.org/a"}, {"title": "Sweets"}],
        "lang": "en",
    }
    seen = fake_http(monkeypatch, lambda req: httpx.Response(200, json=answer))
    reply = await Brain(base=API).handle(text("What should we eat in Goa?"))
    assert json.loads(seen[0].content) == {
        "question": "What should we eat in Goa?",
        "lang": "en",
        "has_elderly": False,
    }
    assert reply == (
        "Try fish curry [1] and bebinca [2].\n\n[1] Goan food https://example.org/a\n[2] Sweets"
    )


async def test_hindi_question_is_answered_in_hindi_with_markers_kept(monkeypatch):
    answer = {"text": "Try fish curry at Fontainhas [1].", "citations": [{"title": "S"}]}

    def handler(req):
        if req.url.host == "translate.test":
            return tagging_translate(req)
        return httpx.Response(200, json=answer)

    seen = fake_http(monkeypatch, handler)
    brain = Brain(base=API, translator=Translator(TRANSLATE))
    reply = await brain.handle(text("गोवा में क्या खाएं?"))
    assert json.loads(seen[0].content)["lang"] == "hi"
    sent = json.loads(seen[1].content)
    assert sent["target"] == "hi" and "[1]" in sent["entities"]
    assert reply == "<hi>Try fish curry at Fontainhas [1].\n\n[1] S"


async def test_plan_summary_is_translated_with_place_names_kept(monkeypatch):
    def handler(req):
        if req.url.host == "translate.test":
            return tagging_translate(req)
        return httpx.Response(200, text=sse(done()))

    seen = fake_http(monkeypatch, handler)
    brain = Brain(base=API, translator=Translator(TRANSLATE))
    reply = await brain.handle(text("मुझे गोवा की यात्रा करनी है"))
    assert json.loads(seen[0].content)["lang"] == "hi"
    sent = json.loads(seen[1].content)
    assert "Basilica of Bom Jesus" in sent["entities"] and "Bengaluru" in sent["entities"]
    assert all(line.startswith("<hi>") for line in reply.split("\n"))


async def test_flagged_translation_stays_english(monkeypatch):
    def handler(req):
        if req.url.host == "translate.test":
            n = len(json.loads(req.content)["texts"])
            return httpx.Response(
                200,
                json={"translations": ["x"] * n, "target": "hi", "via": [], "flags": [["length"]] * n},
            )
        return httpx.Response(200, json={"text": "Fish curry.", "lang": "en"})

    fake_http(monkeypatch, handler)
    brain = Brain(base=API, translator=Translator(TRANSLATE))
    assert await brain.handle(text("गोवा में क्या खाएं?")) == "Fish curry."


async def test_location_is_sent_with_emergency_questions(monkeypatch):
    clock = Clock()
    answer = {
        "text": "The nearest hospital is close by.",
        "emergency_places": [
            {
                "id": "h1",
                "name": "Sample Hospital",
                "lat": 15.5,
                "lng": 73.8,
                "category": "hospital",
                "typical_visit_minutes": 0,
                "source": "places",
            }
        ],
    }
    seen = fake_http(monkeypatch, lambda req: httpx.Response(200, json=answer))
    brain = Brain(base=API, clock=clock)
    loc = {"from": "15550001111", "type": "location", "location": {"latitude": 15.5, "longitude": 73.8}}
    assert (await brain.handle(loc)).startswith("Got your location")
    reply = await brain.handle(text("nearest hospital"))
    body = json.loads(seen[0].content)
    assert (body["lat"], body["lng"]) == (15.5, 73.8)
    assert "Sample Hospital https://maps.google.com/?q=15.5,73.8" in reply
    clock.now += 61 * 60
    await brain.handle(text("nearest hospital"))
    assert "lat" not in json.loads(seen[1].content)


async def test_voice_reply_uses_the_users_last_language(monkeypatch):
    fake_http(monkeypatch, tagging_translate)
    brain = Brain(base="", translator=Translator(TRANSLATE))
    brain.users["15550001111"] = User(lang=Lang.ta)
    reply = await brain.handle({"from": "15550001111", "type": "audio"})
    assert reply.startswith("<ta>Sorry")


async def test_translate_down_means_english(monkeypatch):
    fake_http(monkeypatch, lambda req: httpx.Response(503))
    out = await Translator(TRANSLATE).text("Hello [1].", Lang.hi)
    assert out == "Hello [1]."


async def test_dropped_marker_keeps_english(monkeypatch):
    def handler(req):
        n = len(json.loads(req.content)["texts"])
        return httpx.Response(
            200, json={"translations": ["नमस्ते"] * n, "target": "hi", "via": [], "flags": [[]] * n}
        )

    fake_http(monkeypatch, handler)
    assert await Translator(TRANSLATE).text("Hello [1].", Lang.hi) == "Hello [1]."


async def test_long_lines_are_split_for_translate(monkeypatch):
    seen = fake_http(monkeypatch, tagging_translate)
    line = " ".join(["This is a sentence."] * 80)
    out = await Translator(TRANSLATE).text(line, Lang.hi)
    assert all(len(t) <= 1000 for t in json.loads(seen[0].content)["texts"])
    assert out.count("<hi>") == 80


async def test_long_answers_are_capped(monkeypatch):
    fake_http(monkeypatch, lambda req: httpx.Response(200, json={"text": "x" * 5000}))
    reply = await Brain(base=API).handle(text("Tell me everything about Hampi"))
    assert len(reply) == MAX_REPLY


async def test_plan_error_event_raises(monkeypatch):
    fake_http(
        monkeypatch,
        lambda req: httpx.Response(200, text=sse({"stage": "error", "message": "no route"})),
    )
    with pytest.raises(RuntimeError, match="no route"):
        await Brain(base=API).handle(text("Plan Bengaluru to Goa 11-14 Dec"))


async def test_overlong_sentence_stays_english_and_whole(monkeypatch):
    seen = fake_http(monkeypatch, tagging_translate)
    line = "y" * 1500 + ". Short one."
    out = await Translator(TRANSLATE).text(line, Lang.hi)
    assert json.loads(seen[0].content)["texts"] == ["Short one."]
    assert out == "y" * 1500 + ". <hi>Short one."


async def test_many_pieces_are_sent_in_batches_of_200(monkeypatch):
    seen = fake_http(monkeypatch, tagging_translate)
    out = await Translator(TRANSLATE).texts([f"Line {i}." for i in range(450)], Lang.hi)
    assert [len(json.loads(r.content)["texts"]) for r in seen] == [200, 200, 50]
    assert all(t.startswith("<hi>") for t in out)


async def test_latin_answer_keeps_hindi_mid_plan(monkeypatch):
    replies = iter(
        [
            sse({"stage": "needs_input", "message": "q", "questions": ["How many?"]}),
            sse(done()),
        ]
    )
    seen = fake_http(monkeypatch, lambda req: httpx.Response(200, text=next(replies)))
    brain = Brain(base=API)
    await brain.handle(text("मुझे गोवा की यात्रा करनी है"))
    await brain.handle(text("4 people, train"))
    assert json.loads(seen[1].content)["lang"] == "hi"


async def test_question_mid_plan_goes_to_guide_and_keeps_pending(monkeypatch):
    def handler(req):
        if req.url.path == "/plan":
            ask = {"stage": "needs_input", "message": "q", "questions": ["When?"]}
            return httpx.Response(200, text=sse(ask))
        return httpx.Response(200, json={"text": "Fish curry."})

    seen = fake_http(monkeypatch, handler)
    brain = Brain(base=API)
    await brain.handle(text("Plan a trip to Goa"))
    assert await brain.handle(text("What should we eat there?")) == "Fish curry."
    assert seen[1].url.path == "/guide/ask"
    assert brain.users["15550001111"].pending == "Plan a trip to Goa"


async def test_failed_plan_keeps_the_pending_text(monkeypatch):
    calls = iter(
        [
            httpx.Response(
                200, text=sse({"stage": "needs_input", "message": "q", "questions": ["When?"]})
            ),
            httpx.Response(503),
        ]
    )
    fake_http(monkeypatch, lambda req: next(calls))
    brain = Brain(base=API)
    await brain.handle(text("Plan a trip to Goa"))
    with pytest.raises(httpx.HTTPStatusError):
        await brain.handle(text("11-14 Dec"))
    assert brain.users["15550001111"].pending == "Plan a trip to Goa"


async def test_long_answer_keeps_its_sources(monkeypatch):
    answer = {"text": "x" * 5000 + " [1]", "citations": [{"title": "Goan food"}]}
    fake_http(monkeypatch, lambda req: httpx.Response(200, json=answer))
    reply = await Brain(base=API).handle(text("Tell me everything about Goa"))
    assert len(reply) <= MAX_REPLY and reply.endswith("\n\n[1] Goan food")


@pytest.mark.parametrize("body", [{"oops": 1}, [], {"translations": ["a"], "flags": []}])
async def test_malformed_translate_response_stays_english(monkeypatch, body):
    fake_http(monkeypatch, lambda req: httpx.Response(200, json=body))
    assert await Translator(TRANSLATE).text("Hello [1].", Lang.hi) == "Hello [1]."


async def test_on_cloud_run_translate_gets_a_cached_id_token(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "ty-bots")

    def handler(req):
        if req.url.host == "metadata.google.internal":
            assert req.headers["metadata-flavor"] == "Google"
            assert req.url.params["audience"] == "https://translate.example"
            return httpx.Response(200, text="id-token-1")
        assert req.headers["authorization"] == "Bearer id-token-1"
        return tagging_translate(req)

    seen = fake_http(monkeypatch, handler)
    tr = Translator("https://translate.example")
    await tr.text("Hello.", Lang.hi)
    await tr.text("Again.", Lang.hi)
    hosts = [r.url.host for r in seen]
    assert hosts.count("metadata.google.internal") == 1 and hosts.count("translate.example") == 2


async def test_local_translate_sends_no_token(monkeypatch):
    monkeypatch.delenv("K_SERVICE", raising=False)
    seen = fake_http(monkeypatch, tagging_translate)
    await Translator("https://translate.example").text("Hello.", Lang.hi)
    assert "authorization" not in seen[0].headers


async def test_no_token_means_english(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "ty-bots")
    fake_http(monkeypatch, lambda req: httpx.Response(500))
    assert await Translator("https://translate.example").text("Hello.", Lang.hi) == "Hello."
