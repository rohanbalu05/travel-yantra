"""Pipeline steps. Each takes the session state (plain JSON) and the model and returns (state_delta, message).

Only intake (Flash-Lite), story (Flash-Lite) and narrator (Flash) call the model; the rest is deterministic.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache

from ty_contracts import (
    Itinerary,
    KathaStory,
    Lang,
    Leg,
    Mode,
    Place,
    PlanText,
    SeasonNote,
    Stay,
    TransportOption,
    TripDraft,
    TripRequest,
    Violation,
)

from . import fakes
from .checker import budget, check
from .intake import intake as run_intake
from .llm import Model
from .repair import finish, repair
from .solver import ELDERLY_AGE, RETURN_DEPART, Travel, journey, solve_trip, split_days

# Inter-city road hops leave at this time when routes has no timetable for them.
HOP_DEPART = time(8, 0)
LANG_NAME = {Lang.en: "English", Lang.hi: "Hindi", Lang.kn: "Kannada", Lang.ta: "Tamil", Lang.te: "Telugu", Lang.bn: "Bengali"}


def _dump(items) -> list:
    return [x.model_dump(mode="json", by_alias=True) for x in items]


def _request(state: dict) -> TripRequest:
    return TripRequest.model_validate(state["request"])


def _itinerary(state: dict) -> Itinerary:
    return Itinerary.model_validate(state["itinerary"])


def _draft(d) -> dict:
    """The intake draft as a TripDraft for the client's pre-filled form; unusable ages are left out."""
    travellers = [{"name": t.name, "age": t.age} for t in d.travellers if 0 <= t.age <= 120]
    return TripDraft(origin=d.origin, destinations=d.destinations, start_date=d.start_date, end_date=d.end_date,
                     budget_inr=d.budget_inr if d.budget_inr is None or d.budget_inr >= 0 else None,
                     pace=d.pace, travellers=travellers).model_dump(mode="json")


async def intake(state: dict, model: Model):
    body = state["body"]
    parsed = PlanText.model_validate(body) if "text" in body else TripRequest.model_validate(body)
    result = await run_intake(parsed, model)
    if result.request is None:
        draft = _draft(result.draft) if result.draft else None
        return {"questions": result.questions, "draft": draft}, "I need a little more to plan this"
    r = result.request
    return {"request": r.model_dump(mode="json")}, f"Planning {r.origin} to {', '.join(r.destinations)}"


@lru_cache
def _compare():
    # TY3's in-process service; it loads the rail graph once.
    from routes.compare import get_service

    return get_service()


@lru_cache(maxsize=256)
def _compared(origin: str, destination: str, day: date, depart: time = time(8, 0)) -> tuple[TransportOption, ...]:
    """Cached per route, day and departure time: the graph search is deterministic for the same inputs."""
    from routes.compare import CompareRequest, UnknownPlace

    try:
        found = _compare().compare(CompareRequest(origin=origin, destination=destination, date=day, depart_time=depart))
    except UnknownPlace:
        return ()
    return tuple(o.option for o in found.options)


def transport_options(request: TripRequest) -> list[TransportOption]:
    """Ranked options from TY3's /routes/compare service for origin to first destination (one way).
    Falls back to the sample options when routes does not know a city."""
    options = [o.model_copy(deep=True) for o in _compared(request.origin, request.destinations[0], request.start_date)]
    return options or fakes.transport(request)


async def transport(state: dict, model: Model):
    r = _request(state)
    options = transport_options(r)
    journeys = hops(r, options)
    back = home(r)
    more = f" and {len(journeys) - 1} between cities" if len(journeys) > 1 else ""
    return ({"transport": _dump(options),
             "hops": {c: leg.model_dump(mode="json", by_alias=True) for c, leg in journeys.items()},
             "home": back.model_dump(mode="json", by_alias=True) if back else None},
            f"Found {len(options)} ways to travel{more}")




def city_places(request: TripRequest, city: str) -> list[Place]:
    """Ranked places for one city from TY2's corpus planner (Karnataka); samples where it has none."""
    from guide.planner import places_for

    elderly = bool(request.constraints.mobility_needs) or any(t.age >= ELDERLY_AGE for t in request.constraints.travellers)
    return places_for(city, elderly=elderly) or fakes.places(request.model_copy(update={"destinations": [city]}))


def place_options(request: TripRequest) -> list[Place]:
    return [p for city in request.destinations for p in city_places(request, city)]


async def places(state: dict, model: Model):
    r = _request(state)
    pools = {city: city_places(r, city) for city in r.destinations}
    found = sum(len(v) for v in pools.values())
    return {"pools": {c: _dump(v) for c, v in pools.items()}}, f"Found {found} places to see"


def hop(request: TripRequest, a: str, b: str, day: date, depart: time = HOP_DEPART) -> Leg | None:
    """The journey from a to b on `day`, leaving around `depart`: TY3's best-ranked option, or a road
    estimate between the two cities' top places when routes does not know a city."""
    found = _compared(a, b, day, depart)
    if found:
        return journey(a, b, found[0])
    pa, pb = city_places(request, a), city_places(request, b)
    if not pa or not pb:
        return None
    minutes, cost = Travel().edge(pa[0], pb[0])
    leave = datetime.combine(day, depart)
    return Leg(**{"from": a}, to=b, mode=Mode.road, depart=leave, arrive=leave + timedelta(minutes=minutes),
               minutes=minutes, cost_inr=cost)


def hops(request: TripRequest, options: list[TransportOption]) -> dict[str, Leg]:
    """The journey into each destination on its first day: from the origin on the chosen transport option
    for the first city, then city to city."""
    split = [(c, d) for c, d in split_days(request) if d]
    out = {}
    if split:
        first, dates = split[0]
        leg = journey(request.origin, first, options[0]) if options else hop(request, request.origin, first, dates[0])
        if leg is not None:
            out[first] = leg
    for (prev, _), (city, dates) in zip(split, split[1:]):
        if (leg := hop(request, prev, city, dates[0])) is not None:
            out[city] = leg
    return out


def home(request: TripRequest) -> Leg | None:
    """The journey back to the origin from the last city, in the evening of the last day."""
    split = [(c, d) for c, d in split_days(request) if d]
    if not split:
        return None
    last, dates = split[-1]
    return hop(request, last, request.origin, dates[-1], RETURN_DEPART)


def city_stays(request: TripRequest, city: str, check_in: date, nights: int) -> list[Stay]:
    """Ranked stays from TY3's routes.stays; sample stays for cities it does not cover."""
    from routes.compare import UnknownPlace
    from routes.stays import rank_stays

    people = max(len(request.constraints.travellers), 1)
    check_out = check_in + timedelta(days=nights)
    try:
        found = rank_stays(city, check_in, check_out, party=people, limit=3)
    except (UnknownPlace, ValueError):
        found = []
    if found:
        return found
    one = request.model_copy(update={"destinations": [city]})
    return [s.model_copy(update={"check_in": check_in, "check_out": check_out}) for s in fakes.stays(one)]


def stay_options(request: TripRequest) -> list[Stay]:
    """Stays for each city's nights, in trip order. The last city loses a night to the day you leave."""
    split = [(c, d) for c, d in split_days(request) if d]
    out: list[Stay] = []
    for n, (city, dates) in enumerate(split):
        nights = len(dates) - (1 if n == len(split) - 1 else 0)
        if nights > 0 or len(split) == 1:
            out += city_stays(request, city, dates[0], max(nights, 1))
    return out


async def stays(state: dict, model: Model):
    found = stay_options(_request(state))
    return {"stays": _dump(found)}, f"Found {len(found)} stays"


async def story(state: dict, model: Model):
    r = _request(state)
    found = place_options(r)
    subject = found[0].name if found else r.destinations[0]
    text = await model.text(
        f"Tell a short, warm story (about 120 words) about {subject} for a family visiting it. "
        f"Write in {LANG_NAME[r.lang]}. Plain text, no headings. Only well-known history; say 'it is said' for legends.",
        tier="lite", thinking="minimal",
    )
    katha = KathaStory(subject_kind="place", subject=subject, length_min=2, lang=r.lang, text=text, sources=["model"])
    return {"story": katha.model_dump(mode="json")}, f"Story ready for {subject}"


def _missing_stays(request: TripRequest, stays: list[dict]) -> list[str]:
    """A warning for each city that has nights on the trip but no stay to offer yet."""
    check_ins = {Stay.model_validate(s).check_in for s in stays}
    split = [(c, d) for c, d in split_days(request) if d]
    return [f"No stays found yet for {city}" for n, (city, dates) in enumerate(split)
            if (n < len(split) - 1 or len(split) == 1 or len(dates) > 1) and dates[0] not in check_ins]


def assemble(r: TripRequest, pools: dict[str, list[Place]], options: list[TransportOption], journeys: dict[str, Leg],
             back: Leg | None, stays_found: list[Stay]) -> Itinerary:
    """Solve the days and put the itinerary together with its budget and warnings."""
    days, _ = solve_trip(r, pools, journeys, home=back)
    empty = [c for c, v in pools.items() if not v]
    it = Itinerary(
        request=r, days=days, lang=r.lang, transport=options, stays=stays_found,
        budget={"transport_inr": 0, "stay_inr": 0, "total_inr": 0},
        # Unused candidates are not a problem (the planner offers more than a trip holds); an empty pool is.
        warnings=[f"No places found yet for {c}" for c in empty]
        + _missing_stays(r, [s.model_dump(mode="json") for s in stays_found]),
        season_notes=season_notes(r),
    )
    it.budget = budget(it)
    return it


def season_notes(r: TripRequest) -> list[SeasonNote]:
    """TY2's quoted season notes for each city and each month the trip spends there. Nothing is added when
    the sources say nothing (no guessing)."""
    from guide.season import notes_for

    out: list[SeasonNote] = []
    seen: set[tuple[str, str]] = set()
    for city, dates in split_days(r):
        for month in dict.fromkeys(d.month for d in dates):
            for n in notes_for(city, next(d for d in dates if d.month == month)):
                if (city, n["text"]) not in seen:
                    seen.add((city, n["text"]))
                    out.append(SeasonNote(city=city, text=n["text"], source_url=n["source_url"], kind=n["kind"]))
    return out


def replan(r: TripRequest) -> Itinerary:
    """The whole deterministic plan for a request, without the agents (revise uses it)."""
    options = transport_options(r)
    pools = {city: city_places(r, city) for city in r.destinations}
    return assemble(r, pools, options, hops(r, options), home(r), stay_options(r))


async def solver(state: dict, model: Model):
    r = _request(state)
    it = assemble(
        r,
        {c: [Place.model_validate(p) for p in v] for c, v in state["pools"].items()},
        [TransportOption.model_validate(t) for t in state["transport"]],
        {c: Leg.model_validate(v) for c, v in state.get("hops", {}).items()},
        Leg.model_validate(state["home"]) if state.get("home") else None,
        [Stay.model_validate(s) for s in state["stays"]],
    )
    stops = sum(len(d.stops) for d in it.days)
    return {"itinerary": it.model_dump(mode="json", by_alias=True)}, f"Planned {stops} stops over {len(it.days)} days"


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
