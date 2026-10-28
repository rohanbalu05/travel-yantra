"""The four regions (HQ P10): help names them and voice notes; trips elsewhere get a polite no."""

import pytest
from conftest import asks, done, send, sse, texts

from ty_chat import text as rules
from ty_chat.engine import HELP, outside


def test_help_names_the_regions_and_voice_notes():
    for word in ("Karnataka", "Goa", "Kerala", "Golden Triangle", "voice note"):
        assert word in HELP


@pytest.mark.parametrize(
    "said, far",
    [
        ("Plan Bengaluru to Manali, 11-14 Dec, 4 of us", ["Manali"]),
        ("Chennai to Ooty trip next weekend", ["Ooty"]),
        ("plan a trip to Ladakh", ["Ladakh"]),
        ("Plan Bengaluru to Goa, 11-14 Dec", []),
        ("Plan Chennai to Munnar 3-5 Jan", []),  # the origin can be anywhere
        ("Delhi to Agra and Jaipur trip, 2-6 Feb", []),
        ("plan a trip for Arjun and family", []),  # "for X" may be a person
        ("Bangalore to Mysore trip", []),
        ("Mumbai to Ernakulam trip, 2-4 Mar", []),
        ("visit Pink City and Amer", []),
        ("Plan Bengaluru to Mysore Palace", []),
        ("plan trip to Ooty and Goa", []),
        ("visit Kerala Backwaters", []),
        ("Bengaluru to Nagarhole trip", []),
        ("Plan a trip to Cameroon", ["Cameroon"]),
    ],
)
def test_outside_regions(said, far):
    assert rules.outside_regions(rules.destinations(said, strict=True), said) == far


def test_same_place_edges():
    assert rules.same_place("Goa", ["North Goa"]) and rules.same_place("Mysore", ["Mysuru"])
    assert not rules.same_place("Goa", ["१२"]) and not rules.same_place("12", ["Goa"])
    assert rules.same_place("मैसूर", ["मैसूर पैलेस"]) and not rules.same_place("मैसूर", ["मसूरी"])


async def test_trip_outside_the_regions_is_not_planned(engine, api):
    events = await send(engine, "Plan Bengaluru to Manali, 11-14 Dec, 4 of us")
    assert texts(events) == [outside(["Manali"])] and not api.bodies("/plan")


async def test_planner_draft_outside_the_regions(engine, api):
    # Lower-case or Indic names the rules miss: the planner's own reading decides.
    api.plans = [sse(asks("Which dates?", draft={"destinations": ["Shimla"]}))]
    events = await send(engine, "शिमला की यात्रा")
    assert texts(events) == [outside(["Shimla"])]
    assert (await engine.store.get("test-client-0001")).draft == []


async def test_covered_trip_still_plans(engine, api):
    api.plans = [sse(done())]
    await send(engine, "Plan Bengaluru to Goa, 11-14 Dec, 4 of us")
    assert len(api.bodies("/plan")) == 1
