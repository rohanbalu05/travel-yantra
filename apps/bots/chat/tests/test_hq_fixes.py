"""HQ D-54 (no validation text), D-58 (mode chips) and the budget parts line."""

import httpx
import pytest
from conftest import ITINERARY, done, of, send, sse, texts
from ty_contracts import Itinerary, Mode

from ty_chat import engine as engine_mod
from ty_chat.engine import CANT_CHANGE, WHICH_PLACE, budget_parts, next_hint, summarise


@pytest.fixture
async def planned(engine, api):
    api.plans = [sse(done())]
    await send(engine, "Plan Bengaluru to Goa, 11-14 Dec, 4 of us")
    return engine


def refusing(api, status: int, detail):
    orig = api.handler

    def handler(req):
        if req.url.path.endswith("/revise"):
            api.requests.append(req)
            return httpx.Response(status, json={"detail": detail})
        return orig(req)

    return httpx.MockTransport(handler)


async def test_validation_text_is_never_shown(planned, api, caplog):
    raw = [{"type": "value_error", "msg": "Value error, add_stop needs place or place_id"}]
    planned.api.transport = refusing(api, 422, raw)
    events = await send(planned, "add Fort Aguada on day 2")
    assert texts(events) == [CANT_CHANGE]
    assert "Value error" not in " ".join(texts(events))
    assert "add_stop needs place" in caplog.text  # the raw words go to the log


async def test_a_string_validation_message_is_not_shown_either(planned, api):
    planned.api.transport = refusing(api, 422, "Value error, move_stop needs place_id and day")
    assert texts(await send(planned, "add Fort Aguada on day 2")) == [CANT_CHANGE]


async def test_ty1_sentences_are_still_shown(planned, api):
    planned.api.transport = refusing(api, 422, "Sat 12 Dec is full with Dudhsagar Falls")
    assert texts(await send(planned, "add Fort Aguada on day 2")) == [
        "Sat 12 Dec is full with Dudhsagar Falls"
    ]


@pytest.mark.parametrize(
    "said, intent, place",
    [
        ("remove another place on day 2", "remove_stop", "another place on day 2"),
        ("add another stop at Fort Aguada on day 2", "add_stop", "Fort Aguada"),
        ("add another place", "add_stop", None),
        ("more places on day 2", "add_stop", None),
    ],
)
def test_add_more_never_steals_other_edits(said, intent, place):
    from ty_chat.text import keyword_edit

    got = keyword_edit(said)
    assert got[0] == intent and got[1]["place"] == place


@pytest.mark.parametrize("said", ["I do not want any more places", "no more places please"])
def test_refusals_are_not_adds(said):
    from ty_chat.text import keyword_edit

    assert keyword_edit(said) is None


@pytest.mark.parametrize(
    "detail, shown",
    [
        ("List should have at least 1 item after validation", False),
        ("Assertion failed, bad", False),
        ("Not Found", False),
        ("Day 2 needs days off to rest", True),
        ("Sat 12 Dec is full with Dudhsagar Falls; it fits on Fri 11 Dec", True),
    ],
)
def test_which_api_words_travellers_see(detail, shown):
    from ty_chat.api import ApiError

    assert ApiError(422, detail).readable is shown


async def test_more_places_asks_which_until_ty1_ships_it(planned, api):
    events = await send(planned, "more places on day 2")
    assert texts(events) == [WHICH_PLACE] and not api.bodies("/plan/p1/revise")


async def test_more_places_sends_a_day_once_live(planned, api, monkeypatch):
    monkeypatch.setattr(engine_mod, "ADD_ANY_LIVE", True)
    api.revisions = [sse(done())]
    await send(planned, "something else to do on day 2")
    body = api.bodies("/plan/p1/revise")[0]
    assert body["intent"] == "add_stop" and "place" not in body and body["count"] == 2
    assert body["day"] == ITINERARY["days"][1]["date"]


def test_mode_chips_never_offer_the_current_mode():
    it = Itinerary.model_validate(ITINERARY)  # by train; the sample has rail and road options
    _, chips = next_hint(it)
    assert "by train" not in chips
    modes = {o.mode.value for o in it.transport}
    assert ("by road" in chips) == ("road" in modes) and ("fly" in chips) == ("air" in modes)


def test_mode_chips_for_a_road_plan():
    it = Itinerary.model_validate(ITINERARY)
    road = it.transport[0].model_copy(update={"mode": Mode.road})
    it = it.model_copy(update={"transport": [road, it.transport[0]]})
    it.request.transport_mode = Mode.road
    hint, chips = next_hint(it)
    assert "by road" not in chips and "by train" in chips and "by train" in hint


def test_budget_parts_line():
    it = Itinerary.model_validate(ITINERARY)
    b = it.budget.model_copy(
        update={"transport_inr": 2333, "stay_inr": 1906, "food_inr": 3000,
                "activities_inr": 2100, "local_transport_inr": 590, "total_inr": 9929}
    )  # fmt: skip
    it = it.model_copy(update={"budget": b})
    assert budget_parts(it) == [
        "Journeys ₹2,333", "Stay ₹1,906", "Food ₹3,000", "Tickets ₹2,100", "Getting around ₹590",
    ]  # fmt: skip
    body = summarise(it)
    assert "Budget: ₹9,929 total" in body
    assert "  Journeys ₹2,333 · Stay ₹1,906 · Food ₹3,000 · Tickets ₹2,100 · Getting around ₹590" in body


async def test_plan_refused_with_validation_text(engine, api):
    orig = api.handler

    def handler(req):
        if req.url.path == "/plan":
            api.requests.append(req)
            return httpx.Response(422, json={"detail": [{"msg": "Field required"}]})
        return orig(req)

    engine.api.transport = httpx.MockTransport(handler)
    events = await send(engine, "Plan Bengaluru to Goa, 11-14 Dec, 4 of us")
    assert "Field required" not in texts(events)[0] and "where you start" in texts(events)[0]
    assert of(events, "done")
