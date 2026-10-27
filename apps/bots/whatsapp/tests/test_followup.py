import json

import httpx
import pytest
from test_brain import ITINERARY, done, fake_http, sse, text

from app.brain import EXPIRED, PLANNING, WHICH_DAY, Brain, parse_followup

API = "http://api.test"
STOPS = [p for d in ITINERARY["days"] for p in d["stops"]]


@pytest.mark.parametrize(
    "msg, parsed",
    [
        ("share", ("share", None, None)),
        ("Share!", ("share", None, None)),
        ("शेयर", ("share", None, None)),
        ("make day 2 lighter", ("lighter_day", 2, None)),
        ("lighter day 3", ("lighter_day", 3, None)),
        ("2nd day halka", ("lighter_day", 2, None)),
        ("it will rain", ("rain", None, None)),
        ("rain day 1", ("rain", 1, None)),
        ("बारिश होगी", ("rain", None, None)),
        ("swap Se Cathedral", ("swap_stop", None, "Se Cathedral")),
        ("replace miramar on day 3", ("swap_stop", 3, "miramar on day 3")),
        ("What should we eat?", None),
        ("shared taxi to Hampi?", None),
        ("is it raining in Goa?", None),
    ],
)
def test_parse_followup(msg, parsed):
    assert parse_followup(msg) == parsed


async def planned(monkeypatch, handler):
    """A brain with a plan (plan_id p1, share_token s1) already made through the fake API."""
    seen = fake_http(monkeypatch, handler)
    brain = Brain(base=API)
    await brain.handle(text("Plan Bengaluru to Goa 11-14 Dec"))
    return brain, seen


def plan_then(revised=None, status=200, body=None):
    def handler(req):
        if req.url.path == "/plan":
            return httpx.Response(200, text=sse({**done(), "share_token": "s1"}))
        if status != 200:
            return httpx.Response(status, json=body)
        return httpx.Response(
            200, text=sse({**done(revised or ITINERARY), "plan_id": "p2", "share_token": "s2"})
        )

    return handler


async def test_plan_reply_offers_followups(monkeypatch):
    fake_http(monkeypatch, plan_then())
    reply = await Brain(base=API).handle(text("Plan Bengaluru to Goa 11-14 Dec"))
    assert "lighter day 2" in reply and "share" in reply


async def test_share_links_to_the_web_page(monkeypatch):
    monkeypatch.setenv("SHARE_BASE_URL", "https://web.example/")
    brain, _ = await planned(monkeypatch, plan_then())
    reply = await brain.handle(text("share"))
    assert reply.endswith("\n\nhttps://web.example/t/s1/")


async def test_share_falls_back_to_the_api_json(monkeypatch):
    brain, _ = await planned(monkeypatch, plan_then())
    assert (await brain.handle(text("share"))).endswith(f"{API}/trips/s1")


async def test_lighter_day_revises_with_that_days_date(monkeypatch):
    brain, seen = await planned(monkeypatch, plan_then())
    reply = await brain.handle(text("make day 2 lighter"))
    req = seen[-1]
    assert req.url.path == "/plan/p1/revise"
    assert json.loads(req.content) == {
        "intent": "lighter_day",
        "lang": "en",
        "day": ITINERARY["days"][1]["date"],
    }
    assert "Day 1" in reply
    user = brain.users["15550001111"]
    assert (user.plan_id, user.share_token) == ("p2", "s2")


async def test_lighter_needs_a_day(monkeypatch):
    brain, seen = await planned(monkeypatch, plan_then())
    assert await brain.handle(text("make it lighter")) == WHICH_DAY
    assert len(seen) == 1  # no revise call


async def test_day_out_of_range(monkeypatch):
    brain, seen = await planned(monkeypatch, plan_then())
    reply = await brain.handle(text("rain day 9"))
    assert reply.startswith(f"Your plan has days 1 to {len(ITINERARY['days'])}")
    assert len(seen) == 1


async def test_rain_without_a_day_covers_the_trip(monkeypatch):
    brain, seen = await planned(monkeypatch, plan_then())
    await brain.handle(text("it will rain"))
    assert json.loads(seen[-1].content) == {"intent": "rain", "lang": "en"}


async def test_swap_finds_the_stop_by_name(monkeypatch):
    brain, seen = await planned(monkeypatch, plan_then())
    target = STOPS[1]
    await brain.handle(text(f"swap {target['name'].lower()}"))
    assert json.loads(seen[-1].content)["place_id"] == target["id"]


async def test_swap_unknown_stop_lists_the_stops(monkeypatch):
    brain, seen = await planned(monkeypatch, plan_then())
    reply = await brain.handle(text("swap Taj Mahal"))
    assert reply.startswith("I could not find Taj Mahal in your plan") and STOPS[0]["name"] in reply
    assert len(seen) == 1


async def test_expired_plan_is_forgotten(monkeypatch):
    handler = plan_then(status=404, body={"detail": "plan not found"})
    brain, _ = await planned(monkeypatch, handler)
    assert await brain.handle(text("rain day 1")) == EXPIRED
    assert brain.users["15550001111"].itinerary is None


async def test_revise_422_detail_is_shown(monkeypatch):
    handler = plan_then(status=422, body={"detail": [{"msg": "stop not in plan"}]})
    brain, _ = await planned(monkeypatch, handler)
    assert await brain.handle(text("rain day 1")) == "stop not in plan"


async def test_followups_only_after_a_plan(monkeypatch):
    seen = fake_http(monkeypatch, lambda req: httpx.Response(200, json={"text": "Here."}))
    await Brain(base=API).handle(text("share"))
    assert seen[0].url.path == "/guide/ask"


async def test_needs_input_echoes_the_draft(monkeypatch):
    ask = {
        "stage": "needs_input",
        "message": "q",
        "questions": ["Which dates?"],
        "draft": {
            "origin": "Bengaluru",
            "destinations": ["Goa"],
            "travellers": [{"name": "A", "age": 30}] * 4,
        },
    }
    fake_http(monkeypatch, lambda req: httpx.Response(200, text=sse(ask)))
    reply = await Brain(base=API).handle(text("Plan Bengaluru to Goa for 4"))
    assert reply.split("\n")[0] == "So far: Goa from Bengaluru, 4 travellers"
    assert reply.endswith("- Which dates?")


@pytest.mark.parametrize("msg", ["change my dates to 12 Dec", "replace the hotel"])
async def test_loose_swap_words_without_a_stop_are_not_a_swap(monkeypatch, msg):
    plan = plan_then()

    def handler(req):
        if req.url.path == "/guide/ask":
            return httpx.Response(200, json={"text": "Guide reply."})
        return plan(req)

    brain, seen = await planned(monkeypatch, handler)
    assert await brain.handle(text(msg)) == "Guide reply."
    assert seen[-1].url.path == "/guide/ask"


async def test_replace_with_a_real_stop_is_a_swap(monkeypatch):
    brain, seen = await planned(monkeypatch, plan_then())
    await brain.handle(text(f"replace {STOPS[0]['name']}"))
    assert seen[-1].url.path == "/plan/p1/revise"


TWO_CITIES = {
    **ITINERARY,
    "request": {**ITINERARY["request"], "destinations": ["Mysuru", "Coorg"]},
}


@pytest.mark.parametrize(
    "msg, city",
    [
        ("extra day in Coorg", "Coorg"),
        ("one more day in Mysuru please", "Mysuru please"),
        ("more time at Coorg", "Coorg"),
        ("add a day to Mysuru", "Mysuru"),
        ("move a day to Coorg.", "Coorg"),
    ],
)
def test_parse_move_day(msg, city):
    assert parse_followup(msg) == ("move_day", None, city)


async def test_extra_day_moves_a_day_to_that_city(monkeypatch):
    def handler(req):
        if req.url.path == "/plan":
            return httpx.Response(200, text=sse(done(TWO_CITIES)))
        return httpx.Response(200, text=sse({**done(TWO_CITIES), "plan_id": "p2"}))

    brain, seen = await planned(monkeypatch, handler)
    await brain.handle(text("one more day in mysuru please"))
    assert seen[-1].url.path == "/plan/p1/revise"
    assert json.loads(seen[-1].content) == {"intent": "move_day", "lang": "en", "city": "Mysuru"}


async def test_extra_day_in_another_city_lists_the_cities(monkeypatch):
    brain, seen = await planned(
        monkeypatch, lambda req: httpx.Response(200, text=sse(done(TWO_CITIES)))
    )
    reply = await brain.handle(text("extra day in Ooty"))
    assert reply == "Ooty is not a city of this trip. Cities: Mysuru, Coorg"
    assert len(seen) == 1


async def test_hint_offers_extra_day_only_for_several_cities(monkeypatch):
    fake_http(monkeypatch, lambda req: httpx.Response(200, text=sse(done(TWO_CITIES))))
    assert "extra day in Coorg" in await Brain(base=API).handle(text("Plan Mysuru and Coorg trip"))
    one = await Brain(base="").handle(text("Plan Bengaluru to Goa 11-14 Dec"))
    assert "extra day in" not in one


async def test_season_notes_are_quoted_with_sources(monkeypatch):
    notes = [
        {
            "city": "Goa",
            "text": "Monsoon ends by October.",
            "source_url": "https://w.example/g",
            "kind": "general",
        },
        {
            "city": "Goa",
            "text": "December is peak season.",
            "source_url": "https://w.example/d",
            "kind": "month",
        },
        {
            "city": "Goa",
            "text": "Third note.",
            "source_url": "https://w.example/3",
            "kind": "general",
        },
    ]
    with_notes = {**ITINERARY, "season_notes": notes}
    fake_http(monkeypatch, lambda req: httpx.Response(200, text=sse(done(with_notes))))
    reply = await Brain(base=API).handle(text("Plan Bengaluru to Goa 11-14 Dec"))
    assert "Season, Goa: December is peak season. [1]" in reply  # the trip's month first
    assert "Season, Goa: Monsoon ends by October. [2]" in reply
    assert "Third note" not in reply
    assert reply.endswith("[1] https://w.example/d\n[2] https://w.example/g")


async def test_planning_note_goes_out_before_the_plan(monkeypatch):
    fake_http(monkeypatch, plan_then())
    notes = []

    async def notify(t):
        notes.append(t)

    reply = await Brain(base=API).handle(text("Plan Bengaluru to Goa 11-14 Dec"), notify=notify)
    assert notes == [PLANNING] and "Day 1" in reply


async def test_guide_questions_send_no_planning_note(monkeypatch):
    fake_http(monkeypatch, lambda req: httpx.Response(200, json={"text": "Fish curry."}))
    notes = []

    async def notify(t):
        notes.append(t)

    await Brain(base=API).handle(text("What should we eat?"), notify=notify)
    assert notes == []
