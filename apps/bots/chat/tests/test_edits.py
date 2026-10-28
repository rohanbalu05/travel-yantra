"""Plain-word edits: keyword rules first, one Flash-Lite parse otherwise; replies say what changed."""

import base64
import json

import pytest
from conftest import ITINERARY, done, of, send, sse, texts

from ty_chat import text as rules
from ty_chat.engine import CHANGED, NO_PLAN, NOT_HEARD, WHICH_DAY
from ty_chat.lite import Edit

DAY1 = ITINERARY["days"][0]
FIRST_STOP = DAY1["stops"][0]


def revised(what: str = "Day 1 is lighter: Se Cathedral moved to day 2") -> str:
    solving = {"stage": "solving", "step": "solver", "message": what, "partial": ITINERARY}
    return sse({"stage": "intake", "message": "Revising your plan…"}, solving, done())


@pytest.fixture
async def planned(engine, api):
    api.plans = [sse(done())]
    await send(engine, "Plan Bengaluru to Goa, 11-14 Dec, 4 of us")
    return engine


@pytest.mark.parametrize(
    "said, intent, fields",
    [
        ("lighter day 2", "lighter_day", {"day": 2}),
        ("rain day 3", "rain", {"day": 3}),
        ("swap Se Cathedral", "swap_stop", {"place": "Se Cathedral", "day": None}),
        ("remove Se Cathedral", "remove_stop", {"place": "Se Cathedral", "day": None}),
        ("skip Se Cathedral", "remove_stop", {"place": "Se Cathedral", "day": None}),
        ("add Fort Aguada on day 2", "add_stop", {"place": "Fort Aguada", "day": 2}),
        ("add Fort Aguada", "add_stop", {"place": "Fort Aguada", "day": None}),
        ("move Se Cathedral to day 3", "move_stop", {"place": "Se Cathedral", "day": 3}),
        ("cheaper hotel please", "change_stay", {"stay_pick": "cheaper"}),
        ("a better rated hotel", "change_stay", {"stay_pick": "better_rated"}),
        ("by train", "transport", {"mode": "rail"}),
        ("let's fly instead", "transport", {"mode": "air"}),
        ("make it luxury", "budget_style", {"style": "luxury"}),
        ("shoestring budget", "budget_style", {"style": "shoestring"}),
        ("running late", "rest_of_day", {"minutes": 30}),
        ("we are late by 1 hour", "rest_of_day", {"minutes": 60}),
        ("45 min late", "rest_of_day", {"minutes": 45}),
        ("extra day in Goa", "move_day", {"city": "Goa"}),
        ("share", "share", {}),
    ],
)
def test_keyword_rules(said, intent, fields):
    assert rules.keyword_edit(said) == (intent, fields)


@pytest.mark.parametrize(
    "said",
    ["is it raining in Goa?", "what time does the Se Cathedral open", "nearest hospital"],
)
def test_questions_are_not_edits(said):
    assert rules.keyword_edit(said) is None


async def test_keyword_edit_calls_revise_without_the_model(planned, api, lite):
    api.revisions = [revised()]
    events = await send(planned, "lighter day 1")
    body = api.bodies("/plan/p1/revise")[0]
    assert body == {"intent": "lighter_day", "lang": "en", "day": DAY1["date"]}
    assert lite.edits == []
    assert texts(events)[0].startswith("Day 1 is lighter: Se Cathedral moved to day 2")
    assert of(events, "done")[0].plan_changed is True


async def test_stop_names_become_place_ids(planned, api):
    api.revisions = [revised("Removed Se Cathedral")]
    await send(planned, f"remove {FIRST_STOP['name'].lower()}")
    assert api.bodies("/plan/p1/revise")[0]["place_id"] == FIRST_STOP["id"]


async def test_unknown_stop_lists_the_stops(planned, api):
    events = await send(planned, "remove Taj Mahal")
    assert "could not find Taj Mahal" in texts(events)[0] and FIRST_STOP["name"] in texts(events)[0]
    assert not api.bodies("/plan/p1/revise")


async def test_flash_lite_parses_once_when_no_rule_matches(planned, api, lite):
    lite.next_edit = Edit(intent="add_stop", place="Fort Aguada", day=2)
    api.revisions = [revised("")]
    events = await send(planned, "we would love to squeeze in Fort Aguada on the second day")
    assert len(lite.edits) == 1
    body = api.bodies("/plan/p1/revise")[0]
    assert body["intent"] == "add_stop" and body["place"] == "Fort Aguada"
    assert body["day"] == ITINERARY["days"][1]["date"]
    # The API gave no words for the change: the reply says it itself.
    assert texts(events)[0].startswith(CHANGED["add_stop"].format(place="Fort Aguada"))


async def test_flash_lite_none_goes_to_the_guide(planned, api, lite):
    events = await send(planned, "tell everyone I said hello")
    assert len(lite.edits) == 1 and texts(events) == ["The guide's answer."]


async def test_questions_skip_the_model(planned, api, lite):
    await send(planned, "where can we eat fish curry?")
    assert lite.edits == [] and api.bodies("/guide/ask")


async def test_running_late_sends_now(planned, api):
    api.revisions = [revised("Re-planned from 15:30")]
    await send(planned, "running late by 30 min")
    body = api.bodies("/plan/p1/revise")[0]
    assert body["intent"] == "rest_of_day" and "T" in body["now"]


async def test_booked_journey_from_the_model(planned, api, lite):
    lite.next_edit = Edit(
        intent="booked",
        mode="rail",
        ref="17309",
        from_city="Bengaluru",
        to_city="Madgaon",
        depart="2026-12-11T21:00:00",
        arrive="2026-12-12T11:00:00",
    )
    api.revisions = [revised("Fitted around train 17309")]
    await send(planned, "we got tickets on the 17309 leaving 9pm on the 11th")
    booked = api.bodies("/plan/p1/revise")[0]["booked"]
    assert booked["ref"] == "17309" and booked["from"] == "Bengaluru"


async def test_intent_without_a_handler_shows_the_api_words(planned, api, lite):
    import httpx

    lite.next_edit = Edit(intent="add_stop", place="Fort Aguada", day=2)
    orig = api.handler

    def refuse(req):
        if req.url.path.endswith("/revise"):
            api.requests.append(req)
            return httpx.Response(422, json={"detail": "add_stop: this change is not available yet"})
        return orig(req)

    planned.api.transport = httpx.MockTransport(refuse)
    events = await send(planned, "we would love to squeeze in Fort Aguada on the second day")
    assert texts(events) == ["add_stop: this change is not available yet"]
    assert of(events, "done")[0].plan_changed is False


async def test_day_out_of_range(planned, api):
    events = await send(planned, "lighter day 9")
    assert "days 1 to" in texts(events)[0] and WHICH_DAY in texts(events)[0]


async def test_edit_without_a_plan(engine):
    assert texts(await send(engine, "lighter day 2")) == [NO_PLAN]


async def test_expired_plan(planned, api):
    import httpx

    api.handler_404 = True
    orig = api.handler

    def gone(req):
        if req.url.path.endswith("/revise"):
            api.requests.append(req)
            return httpx.Response(404, json={"detail": "plan not found"})
        return orig(req)

    api.handler = gone
    planned.api.transport = httpx.MockTransport(gone)
    events = await send(planned, "rain day 2")
    assert "expired" in texts(events)[0]


async def test_voice_note_is_heard_then_handled(engine, api, lite):
    lite.words = "Plan Bengaluru to Goa, 11-14 Dec, 4 of us"
    api.plans = [sse(done())]
    audio = {"data": base64.b64encode(b"OggS fake").decode(), "mime": "audio/ogg; codecs=opus"}
    events = await send(engine, audio=audio, channel="whatsapp")
    assert of(events, "heard")[0].text == lite.words
    assert lite.heard == [(b"OggS fake", "audio/ogg; codecs=opus")]
    assert api.bodies("/plan")[0]["text"] == lite.words and of(events, "plan")


async def test_voice_notes_are_capped_per_day(engine, lite, clock, monkeypatch):
    from ty_chat import engine as engine_mod

    monkeypatch.setattr(engine_mod, "VOICE_PER_DAY", 2)
    lite.words = "hello"
    audio = {"data": base64.b64encode(b"x").decode(), "mime": "audio/ogg"}
    for _ in range(2):
        await send(engine, audio=audio)
    assert texts(await send(engine, audio=audio)) == [engine_mod.VOICE_CAP]
    assert len(lite.heard) == 2
    clock.now += 86400  # the next day
    await send(engine, audio=audio)
    assert len(lite.heard) == 3


async def test_done_is_sent_when_saving_fails(engine, store, monkeypatch):
    async def broken(cid, conv):
        raise OSError("database down")

    monkeypatch.setattr(store, "put", broken)
    events = await send(engine, "hello")
    assert events[-1].type == "done"


async def test_silent_voice_note(engine, lite):
    audio = {"data": base64.b64encode(b"x").decode(), "mime": "audio/ogg"}
    assert texts(await send(engine, audio=audio)) == [NOT_HEARD]


async def test_bad_base64(engine, lite):
    events = await send(engine, audio={"data": "%%%not base64", "mime": "audio/ogg"})
    assert "could not open" in texts(events)[0] and lite.heard == []


def test_destinations():
    assert rules.destinations("Plan Bengaluru to Goa, 11-14 Dec") == ["Goa"]
    assert rules.destinations("Coorg trip next weekend") == ["Coorg"]
    assert rules.destinations("plan it for 4 of us") == []
    assert rules.destinations("the trip is from Bengaluru in December") == []
    assert rules.same_place("Mysore", ["Mysuru"]) and rules.same_place("Goa", ["North Goa"])


def test_sample_is_json():
    assert json.dumps(ITINERARY)
