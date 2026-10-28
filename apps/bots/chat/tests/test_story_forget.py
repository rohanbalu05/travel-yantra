"""Stories (text, sources, audio in order) and delete my data, ported from the WhatsApp brain."""

import httpx
from conftest import CID, done, of, send, sse, texts

from ty_chat.engine import NO_STORY, STORY_BUSY, sources
from ty_chat.models import Conversation

STORY = {
    "subject_kind": "place",
    "subject": "Mysore Palace",
    "length_min": 2,
    "lang": "hi",
    "text": "मैसूर पैलेस की कथा",
    "sources": ["https://example.org/palace"],
    "audio": [
        {"chapter": 2, "url": "https://audio.example/2.mp3", "voice": "hi-IN-x", "characters": 9},
        {"chapter": 1, "url": "https://audio.example/1.mp3", "voice": "hi-IN-x", "characters": 9},
    ],
}


def katha_api(api, status=200, story=STORY):
    orig = api.handler

    def handler(req):
        if req.url.path == "/guide/katha":
            api.requests.append(req)
            return httpx.Response(status, json=story if status == 200 else {"detail": "x"})
        return orig(req)

    return handler


async def test_story_text_sources_then_audio_in_order(engine, api):
    engine.api.transport = httpx.MockTransport(katha_api(api))
    events = await send(engine, "story Mysore Palace in Hindi")
    assert texts(events) == ["मैसूर पैलेस की कथा\n\n[1] https://example.org/palace"]
    assert [e.url for e in of(events, "audio")] == [
        "https://audio.example/1.mp3",
        "https://audio.example/2.mp3",
    ]
    assert of(events, "done")[0].lang == "hi"


async def test_story_audio_that_is_recorded_on_demand(engine, api):
    pending = {**STORY, "audio": [], "audio_status": "pending"}
    answers = [pending, pending, {**STORY, "audio_status": "ready"}]

    def handler(req):
        api.requests.append(req)
        return httpx.Response(200, json=answers.pop(0))

    engine.api.transport = httpx.MockTransport(handler)
    engine.audio_wait = 0
    events = await send(engine, "story Mysore Palace in Hindi")
    kinds = [e.type for e in events]
    assert len(api.requests) == 3 and len(of(events, "audio")) == 2
    assert kinds.index("text") < kinds.index("audio")


async def test_story_audio_still_pending_says_later(engine, api):
    pending = {**STORY, "audio": [], "audio_status": "pending"}

    def handler(req):
        api.requests.append(req)
        return httpx.Response(200, json=pending)

    engine.api.transport = httpx.MockTransport(handler)
    engine.audio_wait = 0
    events = await send(engine, "story Mysore Palace in Hindi")
    assert len(api.requests) == 4 and not of(events, "audio")
    assert "not ready yet" in texts(events)[-1]


async def test_unknown_story_and_busy_storyteller(engine, api):
    engine.api.transport = httpx.MockTransport(katha_api(api, 404))
    assert texts(await send(engine, "story Atlantis")) == [NO_STORY.format(what="Atlantis")]
    # Asked as a place, then as a city.
    assert len([r for r in api.requests if r.url.path == "/guide/katha"]) == 2
    engine.api.transport = httpx.MockTransport(katha_api(api, 503))
    assert texts(await send(engine, "story Hampi")) == [STORY_BUSY]


async def test_delete_my_data_deletes_plans_and_the_conversation(engine, api, store):
    api.plans = [sse(done())]
    await send(engine, "Plan Bengaluru to Goa, 11-14 Dec, 4 of us")
    orig = api.handler

    def handler(req):
        if req.method == "DELETE":
            api.requests.append(req)
            return httpx.Response(204)
        return orig(req)

    engine.api.transport = httpx.MockTransport(handler)
    events = await send(engine, "delete my data")
    assert [r.url.path for r in api.requests if r.method == "DELETE"] == ["/plan/p1"]
    assert "deleted 1 of 1 saved plans" in texts(events)[0]
    assert await store.get(CID) is None
    assert of(events, "done")[0].plan_id is None


async def test_delete_my_data_without_plans(engine, store):
    await store.put(CID, Conversation(draft=["Plan a trip to Goa"], draft_at=1.0))
    events = await send(engine, "forget me")
    assert "I hold no plans" in texts(events)[0] and await store.get(CID) is None


def test_emergency_places_listed_once():
    from ty_contracts import GuideAnswer

    place = {
        "id": "h1", "name": "Sample Hospital", "lat": 15.49871, "lng": 73.82791,
        "category": "hospital", "typical_visit_minutes": 0, "source": "sample",
    }  # fmt: skip
    answer = GuideAnswer(
        text="Call 112. Nearest hospitals below.",
        emergency_places=[place, place, {**place, "id": "h2", "name": "Other Clinic"}],
    )
    assert sources(answer).splitlines() == [
        "[1] Sample Hospital https://maps.google.com/?q=15.4987,73.8279",
        "[2] Other Clinic https://maps.google.com/?q=15.4987,73.8279",
    ]
