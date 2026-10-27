"""Pipeline steps. Each takes the session state (plain JSON) and the model and returns (state_delta, message).

Only intake (Flash-Lite), story (Flash-Lite) and narrator (Flash) call the model; the rest is deterministic.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

from ty_contracts import (
    Itinerary,
    KathaStory,
    Lang,
    Place,
    PlanText,
    Stay,
    TransportOption,
    TripRequest,
    Violation,
)

from . import fakes
from .checker import budget, check
from .intake import intake as run_intake
from .llm import Model
from .repair import finish, repair
from .solver import solve

LANG_NAME = {Lang.en: "English", Lang.hi: "Hindi", Lang.kn: "Kannada", Lang.ta: "Tamil", Lang.te: "Telugu", Lang.bn: "Bengali"}


def _dump(items) -> list:
    return [x.model_dump(mode="json", by_alias=True) for x in items]


def _request(state: dict) -> TripRequest:
    return TripRequest.model_validate(state["request"])


def _itinerary(state: dict) -> Itinerary:
    return Itinerary.model_validate(state["itinerary"])


async def intake(state: dict, model: Model):
    body = state["body"]
    parsed = PlanText.model_validate(body) if "text" in body else TripRequest.model_validate(body)
    result = await run_intake(parsed, model)
    if result.request is None:
        return {"questions": result.questions}, "I need a little more to plan this"
    r = result.request
    return {"request": r.model_dump(mode="json")}, f"Planning {r.origin} to {', '.join(r.destinations)}"


@lru_cache
def _compare():
    # TY3's in-process service; it loads the rail graph once.
    from routes.compare import get_service

    return get_service()


@lru_cache(maxsize=256)
def _compared(origin: str, destination: str, day: date) -> tuple[TransportOption, ...]:
    """Cached per route and day: the graph search is deterministic for the same inputs."""
    from routes.compare import CompareRequest, UnknownPlace

    try:
        found = _compare().compare(CompareRequest(origin=origin, destination=destination, date=day))
    except UnknownPlace:
        return ()
    return tuple(o.option for o in found.options)


def transport_options(request: TripRequest) -> list[TransportOption]:
    """Ranked options from TY3's /routes/compare service for origin to first destination (one way).
    Falls back to the sample options when routes does not know a city."""
    options = [o.model_copy(deep=True) for o in _compared(request.origin, request.destinations[0], request.start_date)]
    return options or fakes.transport(request)


async def transport(state: dict, model: Model):
    options = transport_options(_request(state))
    return {"transport": _dump(options)}, f"Found {len(options)} ways to travel"


# Places are sample-backed until TY2 exposes a places planner.


async def places(state: dict, model: Model):
    found = fakes.places(_request(state))
    return {"places": _dump(found)}, f"Found {len(found)} places to see"


def stay_options(request: TripRequest) -> list[Stay]:
    """Ranked stays from TY3's routes.stays for the first destination; sample stays when it has none."""
    from routes.compare import UnknownPlace
    from routes.stays import rank_stays

    nights = max((request.end_date - request.start_date).days, 1)
    people = max(len(request.constraints.travellers), 1)
    try:
        found = rank_stays(request.destinations[0], request.start_date, request.start_date + timedelta(days=nights),
                           party=people, limit=3)
    except (UnknownPlace, ValueError):
        found = []
    return found or fakes.stays(request)


async def stays(state: dict, model: Model):
    found = stay_options(_request(state))
    return {"stays": _dump(found)}, f"Found {len(found)} stays"


async def story(state: dict, model: Model):
    r = _request(state)
    found = fakes.places(r)
    subject = found[0].name if found else r.destinations[0]
    text = await model.text(
        f"Tell a short, warm story (about 120 words) about {subject} for a family visiting it. "
        f"Write in {LANG_NAME[r.lang]}. Plain text, no headings. Only well-known history; say 'it is said' for legends.",
        tier="lite", thinking="minimal",
    )
    katha = KathaStory(subject_kind="place", subject=subject, length_min=2, lang=r.lang, text=text, sources=["model"])
    return {"story": katha.model_dump(mode="json")}, f"Story ready for {subject}"


async def solver(state: dict, model: Model):
    r = _request(state)
    pool = [Place.model_validate(p) for p in state["places"]]
    days, left = solve(r, pool)
    it = Itinerary(
        request=r, days=days, lang=r.lang,
        transport=[TransportOption.model_validate(t) for t in state["transport"]],
        stays=[Stay.model_validate(s) for s in state["stays"]],
        budget={"transport_inr": 0, "stay_inr": 0, "total_inr": 0},
        warnings=[f"No time left for {p.name}" for p in left]
        + ([] if pool else [f"No places found yet for {', '.join(r.destinations)}"]),
    )
    it.budget = budget(it)
    stops = sum(len(d.stops) for d in days)
    return {"itinerary": it.model_dump(mode="json", by_alias=True)}, f"Planned {stops} stops over {len(days)} days"


async def checker(state: dict, model: Model):
    """One round of the repair loop. Escalates (ends the loop) when the plan is clean."""
    n = state.get("iteration", 0) + 1
    found = check(_itinerary(state))
    delta = {"iteration": n, "violations": [v.model_dump(mode="json") for v in found]}
    return delta, ("Plan checks passed" if not found else f"Found {len(found)} thing{'s' * (len(found) > 1)} to fix")


async def repair_step(state: dict, model: Model):
    found = [Violation.model_validate(v) for v in state.get("violations", [])]
    it, actions = repair(_itinerary(state), found)
    return {"itinerary": it.model_dump(mode="json", by_alias=True)}, "; ".join(actions) or "Nothing more to change"


async def final_check(state: dict, model: Model):
    """After the loop: leftovers become warnings. Returns an empty message when nothing was left."""
    before = _itinerary(state)
    it = finish(before)
    left = len(it.warnings) - len(before.warnings)
    return {"itinerary": it.model_dump(mode="json", by_alias=True)}, (f"{left} issue{'s' * (left > 1)} left as warnings" if left else "")


async def narrator(state: dict, model: Model):
    it = _itinerary(state)
    days = "; ".join(f"{d.date:%a %d %b}: {', '.join(p.name for p in d.stops) or 'free day'}" for d in it.days)
    text = await model.text(
        f"In 2 or 3 friendly sentences in {LANG_NAME[it.lang]}, introduce this trip from {it.request.origin} "
        f"to {', '.join(it.request.destinations)}. Days: {days}. Total about ₹{it.budget.total_inr:,}. "
        "Do not add places or prices that are not listed.",
        tier="flash", thinking="low", max_output_tokens=400,
    )
    return {}, text or "Your trip is ready."
