"""The conversation rules (HQ P8 item 3): answers add to the draft until the plan is made."""

from conftest import ITINERARY, asks, done, of, send, sse, texts

from ty_chat.engine import ASKING, CANCELLED, DRAFT_SECONDS, NOTHING_OPEN, PLANNING
from ty_chat.store import MemoryStore

GOA = {"destinations": ["Goa"], "origin": None}


async def test_answer_with_trip_word_adds_to_the_draft(engine, api):
    # "Goa forgotten twice": the answer says "trip" and "plan", and must not start afresh.
    api.plans = [
        sse(asks("Where from?", "Which dates?", draft=GOA)),
        sse(asks("How many of you?", draft={**GOA, "origin": "Bengaluru"})),
        sse(done()),
    ]
    first = await send(engine, "Plan a trip to Goa")
    assert ASKING in texts(first)[0] and "Goa" in texts(first)[0]
    await send(engine, "the trip is from Bengaluru, 11-14 Dec")
    last = await send(engine, "plan it for 4 of us")
    sent = [b["text"] for b in api.bodies("/plan")]
    assert sent[1] == "Plan a trip to Goa\nthe trip is from Bengaluru, 11-14 Dec"
    assert sent[2] == (
        "Plan a trip to Goa\nthe trip is from Bengaluru, 11-14 Dec\nplan it for 4 of us"
    )
    assert of(last, "plan") and of(last, "done")[0].plan_changed is True


async def test_full_trip_to_the_same_place_still_adds(engine, api):
    api.plans = [sse(asks("How many?", draft=GOA)), sse(done())]
    await send(engine, "Plan a trip to Goa")
    await send(engine, "Bengaluru to Goa 11-14 Dec trip")
    assert api.bodies("/plan")[1]["text"].startswith("Plan a trip to Goa\n")


async def test_a_different_destination_starts_a_new_trip(engine, api):
    api.plans = [sse(asks("Dates?", draft=GOA)), sse(asks("How many?"))]
    await send(engine, "Plan a trip to Goa")
    await send(engine, "Actually plan Bengaluru to Mysuru, 3-4 Nov")
    assert api.bodies("/plan")[1]["text"] == "Actually plan Bengaluru to Mysuru, 3-4 Nov"


async def test_draft_expires_after_30_minutes(engine, api, clock):
    api.plans = [sse(asks("Dates?", draft=GOA))]
    await send(engine, "Plan a trip to Goa")
    clock.now += DRAFT_SECONDS + 1
    events = await send(engine, "11-14 Dec, 4 of us")
    # Not a trip on its own, and the draft is closed: a question for the guide.
    assert len(api.bodies("/plan")) == 1 and api.bodies("/guide/ask")
    assert texts(events) == ["The guide's answer."]


async def test_draft_kept_inside_30_minutes(engine, api, clock):
    api.plans = [sse(asks("Dates?", draft=GOA)), sse(done())]
    await send(engine, "Plan a trip to Goa")
    clock.now += DRAFT_SECONDS - 60
    await send(engine, "11-14 Dec, 4 of us")
    assert api.bodies("/plan")[1]["text"] == "Plan a trip to Goa\n11-14 Dec, 4 of us"


async def test_cancel_closes_the_trip(engine, api):
    api.plans = [sse(asks("Dates?", draft=GOA))]
    await send(engine, "Plan a trip to Goa")
    assert texts(await send(engine, "cancel the trip")) == [CANCELLED]
    await send(engine, "11-14 Dec, 4 of us")
    assert len(api.bodies("/plan")) == 1  # the answer no longer joins a draft
    assert texts(await send(engine, "close the trip")) == [NOTHING_OPEN]


async def test_cancel_my_train_is_not_a_cancel(engine, api):
    api.plans = [sse(asks("Dates?", draft=GOA)), sse(asks("How many?", draft=GOA))]
    await send(engine, "Plan a trip to Goa")
    await send(engine, "cancel my train, we will drive")
    assert len(api.bodies("/plan")) == 2


async def test_full_new_trip_beats_followup_words(engine, api):
    api.plans = [sse(done()), sse(done(plan_id="p2"))]
    await send(engine, "Plan Bengaluru to Goa, 11-14 Dec, 4 of us")
    # "lighter" and "rain" are edit words, but this is a whole trip to a new place.
    await send(engine, "Plan Bengaluru to Mysuru 3-4 Nov, a lighter trip in case of rain")
    assert len(api.bodies("/plan")) == 2 and not any(
        r.url.path.endswith("/revise") for r in api.requests
    )


async def test_no_working_note_when_the_reply_is_only_questions(engine, api):
    intake = {"stage": "intake", "message": "Reading your trip"}
    api.plans = [sse(intake, asks("Which dates?", draft=GOA))]
    events = await send(engine, "Plan a trip to Goa")
    assert not of(events, "note")


async def test_working_note_once_planning_starts(engine, api):
    intake = {"stage": "intake", "message": "Reading your trip"}
    planning = {"stage": "planning", "message": "Finding places", "step": "places"}
    api.plans = [sse(intake, planning, planning, done())]
    events = await send(engine, "Plan Bengaluru to Goa, 11-14 Dec, 4 of us")
    assert [e.text for e in of(events, "note")] == [PLANNING]
    kinds = [e.type for e in events]
    assert kinds.index("note") < kinds.index("plan") < kinds.index("text") < kinds.index("done")


async def test_state_survives_a_restart(api, clock, lite):
    # A new Engine over the same store: as after a Cloud Run restart with Postgres.
    import httpx

    from ty_chat.api import Api
    from ty_chat.engine import Engine

    store = MemoryStore()
    api.plans = [sse(asks("Dates?", draft=GOA)), sse(done())]

    def fresh() -> Engine:
        transport = httpx.MockTransport(api.handler)
        return Engine(Api("http://api", transport), store, lite=lite, clock=clock)

    await send(fresh(), "Plan a trip to Goa")
    events = await send(fresh(), "11-14 Dec from Bengaluru, 4 of us")
    assert api.bodies("/plan")[1]["text"].startswith("Plan a trip to Goa\n")
    assert of(events, "done")[0].plan_id == "p1"
    saved = await store.get("test-client-0001")
    assert saved.plan_id == "p1" and saved.draft == [] and saved.itinerary is not None


async def test_question_mid_draft_goes_to_the_guide_and_keeps_the_draft(engine, api):
    api.plans = [sse(asks("Dates?", draft=GOA)), sse(done())]
    await send(engine, "Plan a trip to Goa")
    assert texts(await send(engine, "is it hot in december?")) == ["The guide's answer."]
    await send(engine, "11-14 Dec, 4 of us")
    assert api.bodies("/plan")[1]["text"] == "Plan a trip to Goa\n11-14 Dec, 4 of us"


async def test_same_destination_trip_words_with_a_plan(engine, api):
    api.plans = [sse(done())]
    await send(engine, "Plan Bengaluru to Goa, 11-14 Dec, 4 of us")
    events = await send(engine, "plan more beaches in Goa")
    assert "already have a plan for Goa" in texts(events)[0]
    assert len(api.bodies("/plan")) == 1


async def test_plan_summary_and_ids(engine, api):
    api.plans = [sse(done())]
    events = await send(engine, "Plan Bengaluru to Goa, 11-14 Dec, 4 of us")
    plan = of(events, "plan")[0]
    assert plan.plan_id == "p1" and plan.share_token == "tok1"
    assert plan.itinerary.request.destinations == ITINERARY["request"]["destinations"]
    body = texts(events)[0]
    assert "Travel: by train" in body and "Journeys:" in body
    assert "per person" in body and "Day 1" in body
    assert of(events, "chips")[0].chips[0] == "share"
