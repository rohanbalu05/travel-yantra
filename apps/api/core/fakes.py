"""Fake pipeline steps. They read the sample trips in packages/contracts/samples; no model or network calls.

Each step takes the session state and returns (state_delta, message). State values are plain JSON.
"""

import json
from functools import lru_cache
from pathlib import Path

from ty_contracts import Itinerary, KathaStory, Lang, StorySegment, TripRequest

SAMPLES = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "samples"


@lru_cache
def _sample(name: str) -> Itinerary:
    data = json.loads((SAMPLES / name).read_text(encoding="utf-8"))
    return Itinerary.model_validate(data["itinerary"])


def _sample_for(request: dict) -> Itinerary:
    wanted = {d.lower() for d in request["destinations"]}
    return _sample("mysuru_weekend.json" if "mysuru" in wanted else "goa_family.json")


def _dump(obj) -> dict | list:
    return json.loads(json.dumps(obj, default=lambda o: o.model_dump(mode="json", by_alias=True)))


def intake(state: dict):
    request = TripRequest.model_validate(state["request"])
    return {"request": request.model_dump(mode="json")}, f"Planning {request.origin} to {', '.join(request.destinations)}"


def transport(state: dict):
    options = _sample_for(state["request"]).transport
    return {"transport": _dump(options)}, f"Found {len(options)} ways to travel"


def places(state: dict):
    days = [d.stops for d in _sample_for(state["request"]).days]
    return {"places": _dump(days)}, f"Picked {sum(map(len, days))} places"


def stays(state: dict):
    found = _sample_for(state["request"]).stays
    return {"stays": _dump(found)}, f"Found {len(found)} stays"


def story(state: dict):
    sample = _sample_for(state["request"])
    subject = sample.days[0].stops[0].name if sample.days[0].stops else sample.request.destinations[0]
    katha = KathaStory(
        subject_kind="place", subject=subject, length_min=2, lang=Lang.en, sources=["sample"],
        text=f"Sample story about {subject}.", segments=[StorySegment(label="history", text=f"Sample history of {subject}.")],
    )
    return {"story": katha.model_dump(mode="json")}, f"Story ready for {subject}"


def solver(state: dict):
    # ponytail: fake solver reuses the sample days and dates; the real solver is TY1-04
    sample = _sample_for(state["request"])
    days = [{**d.model_dump(mode="json", by_alias=True), "stops": stops} for d, stops in zip(sample.days, state["places"])]
    itinerary = {
        **sample.model_dump(mode="json", by_alias=True),
        "request": state["request"], "days": days, "transport": state["transport"], "stays": state["stays"],
        "lang": state["request"]["lang"],
    }
    return {"itinerary": Itinerary.model_validate(itinerary).model_dump(mode="json", by_alias=True)}, "Built a day-by-day plan"


def checker(state: dict):
    itinerary = Itinerary.model_validate(state["itinerary"])
    budget = itinerary.request.constraints.budget_inr
    itinerary.budget.within_budget = None if budget is None else itinerary.budget.total_inr <= budget
    ok = itinerary.budget.within_budget is not False
    return {"itinerary": itinerary.model_dump(mode="json", by_alias=True)}, "Plan checks passed" if ok else "Plan is over budget"


def narrator(state: dict):
    return {}, f"Your trip is ready. {state['story']['text']}"


STEPS = {f.__name__: f for f in (intake, transport, places, stays, story, solver, checker, narrator)}
