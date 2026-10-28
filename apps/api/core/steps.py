"""Pipeline steps. Each takes the session state (plain JSON) and the model and returns (state_delta, message).

Only intake (Flash-Lite), story (Flash-Lite) and narrator (Flash) call the model; the rest is deterministic.
"""

from __future__ import annotations

import asyncio
import math
import os
from datetime import date, datetime, time, timedelta
from functools import lru_cache

from ty_contracts import (
    BudgetStyle,
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
from .solver import (
    ELDERLY_AGE,
    RETURN_BUFFER_MIN,
    RETURN_DEPART,
    SEATS_PER_CAR,
    Travel,
    after_hop,
    day_titles,
    hop_of,
    journey,
    limits,
    out_of,
    rebuild_day,
    schedule,
    solve_trip,
    split_days,
)

# Inter-city road hops leave at this time when routes has no timetable for them.
HOP_DEPART = time(8, 0)
# Real trains: the earliest a morning journey may leave, and where the search for a late-day train starts.
TRAIN_EARLIEST = time(6, 0)
TRAIN_AFTERNOON = time(12, 0)
TRAIN_LIMIT = 30
# Choosing how to travel when the traveller did not: a journey there and back may take this share of the
# trip's waking hours (WAKING_HOURS a day) before a faster way wins; a shoestring trip accepts more.
WAKING_HOURS = 14
FAIR_SHARE = {BudgetStyle.shoestring: 0.4, BudgetStyle.comfort: 0.25, BudgetStyle.luxury: 0.15}
MODE_NOUN = {Mode.rail: "train", Mode.road: "drive", Mode.air: "flight"}
LANG_NAME = {Lang.en: "English", Lang.hi: "Hindi", Lang.kn: "Kannada", Lang.ta: "Tamil", Lang.te: "Telugu", Lang.bn: "Bengali"}


def samples_allowed() -> bool:
    """Sample places, options and stays (fakes.py) fill gaps only in tests and demos (TY_SAMPLE_DATA=1).
    Real users never see sample data presented as real."""
    return os.getenv("TY_SAMPLE_DATA") == "1"


def party(request: TripRequest) -> int:
    return max(len(request.constraints.travellers), 1)


# TY3's words for a budget style (rail class and stay band); None is "mid".
ROUTES_STYLE = {BudgetStyle.shoestring: "budget", BudgetStyle.comfort: "mid", BudgetStyle.luxury: "luxury"}


def routes_style(request: TripRequest) -> str | None:
    style = request.constraints.budget_style
    return ROUTES_STYLE[BudgetStyle(style)] if style else None


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
                     pace=d.pace, travellers=travellers, transport_mode=d.transport_mode,
                     budget_style=d.budget_style).model_dump(mode="json")


def _request_draft(r: TripRequest) -> dict:
    c = r.constraints
    return TripDraft(origin=r.origin, destinations=r.destinations, start_date=r.start_date, end_date=r.end_date,
                     budget_inr=c.budget_inr, pace=c.pace, travellers=c.travellers, transport_mode=r.transport_mode,
                     budget_style=c.budget_style).model_dump(mode="json")


def covers(city: str) -> bool:
    """A destination we can plan: TY2's corpus has places for it (samples too, in tests)."""
    from guide.planner import corpus_city, covered_cities

    return corpus_city(city) in covered_cities() or (samples_allowed() and city.strip().lower() in fakes.BY_CITY)


def regions_text() -> str:
    """"Karnataka (Bengaluru, Mysuru, …), Goa, Kerala (Kochi, …) and the Golden Triangle (Delhi, …)"."""
    from guide.planner import covered_cities

    by_region: dict[str, list[str]] = {}
    for city, region in covered_cities().items():
        by_region.setdefault(region, []).append(city)
    parts = [("the " if region == "Golden Triangle" else "") + region
             + ("" if cities == [region] else f" ({', '.join(cities)})") for region, cities in by_region.items()]
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


def coverage_question(missing: list[str], lang: Lang) -> str:
    places = " and ".join(missing)
    if lang is Lang.hi:
        return f"अभी हम इन जगहों की यात्राएँ बनाते हैं: {regions_text()}। {places} अभी इनमें नहीं है। इनमें से आप कहाँ जाना चाहेंगे?"
    return (f"For now we plan trips in {regions_text()}; {places} is not covered yet. "
            "Where in these would you like to go?")


async def intake(state: dict, model: Model):
    body = state["body"]
    parsed = PlanText.model_validate(body) if "text" in body else TripRequest.model_validate(body)
    result = await run_intake(parsed, model)
    if result.request is None:
        draft = _draft(result.draft) if result.draft else None
        return {"questions": result.questions, "draft": draft}, "I need a little more to plan this"
    r = result.request
    # Outside the regions we cover, say so instead of filling days with places we do not know.
    if missing := [c for c in r.destinations if not await asyncio.to_thread(covers, c)]:
        return ({"questions": [coverage_question(missing, r.lang)], "draft": _request_draft(r)},
                "We do not cover that place yet")
    return {"request": r.model_dump(mode="json")}, f"Planning {r.origin} to {', '.join(r.destinations)}"


@lru_cache
def _compare():
    # TY3's in-process service; it loads the rail graph once.
    from routes.compare import get_service

    return get_service()


@lru_cache(maxsize=256)
def _compared(origin: str, destination: str, day: date, depart: time = time(8, 0),
              travellers: int = 1, rail_class: str | None = None) -> tuple[TransportOption, ...]:
    """Cached per route, day, departure time and party: the graph search is deterministic for the same
    inputs. TY3 prices every option for the whole party (rail and air per person, road per car)."""
    from routes.compare import CompareRequest, UnknownPlace

    try:
        found = _compare().compare(CompareRequest(origin=origin, destination=destination, date=day, depart_time=depart,
                                                  travellers=travellers), rail_class=rail_class)
    except UnknownPlace:
        return ()
    return tuple(o.option for o in found.options)


def chosen_options(request: TripRequest, options: list[TransportOption] | None = None) -> list[TransportOption]:
    """The ranked options with the first one made concrete: when it is rail, the real train the outbound
    journey takes (so the listed option and day 1's journey match)."""
    options = transport_options(request) if options is None else prefer(options, request.transport_mode)
    first = next((c for c, d in split_days(request) if d), None)
    if options and first:
        options = [timed(request, request.origin, first, request.start_date, options[0], "outbound"), *options[1:]]
    return options


def transport_options(request: TripRequest) -> list[TransportOption]:
    """Ranked options from TY3's /routes/compare service for origin to first destination (one way), for the
    party. Nothing when routes does not know a city (sample options only with samples_allowed)."""
    options = [o.model_copy(deep=True) for o in
               _compared(request.origin, request.destinations[0], request.start_date, travellers=party(request),
                         rail_class=routes_style(request))]
    if not options and samples_allowed():
        options = fakes.transport(request)
    return prefer(options, request.transport_mode)


def _hm(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}"


def pick_mode(request: TripRequest, options: list[TransportOption]) -> tuple[Mode | None, str | None]:
    """When the traveller did not choose: weigh door-to-door time against the trip's length. A way whose
    journey there and back takes more than a fair share of the trip's waking hours loses to a faster one;
    among the fair ones the cheapest wins (luxury: the quickest). Returns the mode and the reason, in words."""
    if request.transport_mode or not options:
        return None, None
    best: dict[Mode, TransportOption] = {}
    for o in options:
        best.setdefault(o.mode, o)
    style = request.constraints.budget_style or BudgetStyle.comfort
    days = (request.end_date - request.start_date).days + 1
    awake = days * WAKING_HOURS * 60
    fair = [o for o in best.values() if 2 * o.total_minutes <= FAIR_SHARE[style] * awake]
    quickest = min(best.values(), key=lambda o: (o.total_minutes, o.total_cost_inr))
    if style == BudgetStyle.luxury or not fair:
        pick = quickest
    else:
        pick = min(fair, key=lambda o: (o.total_cost_inr, o.total_minutes))
    noun = MODE_NOUN[pick.mode]
    trip = f"a {days}-day trip"
    slow = sorted((o for o in best.values() if o not in fair and o.total_cost_inr < pick.total_cost_inr),
                  key=lambda o: o.total_cost_inr)
    if len(best) == 1:
        why = f"the only way we found ({_hm(pick.total_minutes)} each way)"
    elif style == BudgetStyle.luxury:
        why = f"the quickest way, {_hm(pick.total_minutes)} door to door, for a luxury trip"
    elif not fair:
        why = f"the quickest way ({_hm(pick.total_minutes)} door to door); every way takes a big part of {trip}"
    elif slow:
        cheaper = slow[0]
        why = (f"the {MODE_NOUN[cheaper.mode]} costs less but takes {_hm(cheaper.total_minutes)} each way, too much "
               f"of {trip}; the {noun} takes {_hm(pick.total_minutes)} door to door")
    else:
        why = f"the cheapest way that keeps travel to a fair part of {trip} ({_hm(pick.total_minutes)} each way)"
    return pick.mode, f"{noun.capitalize()}: {why}."


def plan_transport(r: TripRequest) -> tuple[list[TransportOption], dict[str, Leg], Leg | None, str | None]:
    """The options (the one the days follow first), the journey into each city, the provisional journey home
    and why that mode. Without a chosen mode, pick_mode decides and every journey prefers it."""
    options = transport_options(r)
    mode, reason = pick_mode(r, options)
    rp = r.model_copy(update={"transport_mode": mode}) if mode else r
    options = chosen_options(rp, options)
    return options, hops(rp, options), home(rp), reason


def prefer(options, mode: Mode | None) -> list:
    """The options of the traveller's chosen mode first (in their ranked order), then the rest."""
    if mode is None:
        return list(options)
    return [o for o in options if o.mode is mode] + [o for o in options if o.mode is not mode]


async def transport(state: dict, model: Model):
    r = _request(state)
    options, journeys, back, reason = await asyncio.to_thread(plan_transport, r)
    more = f" and {len(journeys) - 1} between cities" if len(journeys) > 1 else ""
    return ({"transport": _dump(options),
             "hops": {c: leg.model_dump(mode="json", by_alias=True) for c, leg in journeys.items()},
             "home": back.model_dump(mode="json", by_alias=True) if back else None,
             "transport_reason": reason},
            f"Found {len(options)} ways to travel{more}")




def city_places(request: TripRequest, city: str, hours: bool = False) -> list[Place]:
    """Ranked places for one city from TY2's corpus planner; samples where it has none. With hours=True,
    TY2's live_hours fills opening hours from Places where the corpus has a place_id (cached, capped; a no-op
    without DATABASE_URL or a Maps key). That can call the network, so call it off the event loop."""
    from guide.planner import places_for

    elderly = bool(request.constraints.mobility_needs) or any(t.age >= ELDERLY_AGE for t in request.constraints.travellers)
    found = places_for(city, elderly=elderly)
    if found and hours:
        from guide.hours import live_hours

        found = live_hours(found)
    if not found and samples_allowed():
        found = fakes.places(request.model_copy(update={"destinations": [city]}))
    return found


def place_options(request: TripRequest) -> list[Place]:
    return [p for city in request.destinations for p in city_places(request, city)]


async def places(state: dict, model: Model):
    r = _request(state)
    pools = {city: await asyncio.to_thread(city_places, r, city, True) for city in r.destinations}
    found = sum(len(v) for v in pools.values())
    return {"pools": {c: _dump(v) for c, v in pools.items()}}, f"Found {found} places to see"


@lru_cache(maxsize=256)
def _trains(a: str, b: str, day: date, earliest: time, travellers: int = 1,
            rail_class: str | None = None) -> tuple[TransportOption, ...]:
    """TY3's real rail journeys from a to b leaving at or after `earliest` that day, in departure order
    (up to TRAIN_LIMIT, enough to reach the day's last train on these corridors), priced for the party."""
    from routes.compare import UnknownPlace

    try:
        return tuple(_compare().rail_departures(a, b, day, earliest=earliest, limit=TRAIN_LIMIT, travellers=travellers,
                                                rail_class=rail_class))
    except (UnknownPlace, ValueError):
        return ()


def morning_train(request: TripRequest, a: str, b: str, day: date) -> TransportOption | None:
    """The first train after 06:00 that arrives before the day's visits start; else the first after 06:00."""
    trains = _trains(a, b, day, TRAIN_EARLIEST, party(request), routes_style(request))
    start = datetime.combine(day, limits(request).start)
    return next((t for t in trains if t.legs[-1].arrive <= start), trains[0] if trains else None)


def evening_train(request: TripRequest, a: str, b: str, day: date, after: time = RETURN_DEPART) -> TransportOption | None:
    """The first train that leaves at or after `after`; when none leaves that late, the day's last train
    (the checker then trims the visits to make it)."""
    later = _trains(a, b, day, after, party(request), routes_style(request))
    if later:
        return later[0]
    afternoon = _trains(a, b, day, TRAIN_AFTERNOON, party(request), routes_style(request))
    return afternoon[-1] if afternoon else None


def timed(request: TripRequest, a: str, b: str, day: date, option: TransportOption, role: str,
          depart: time = RETURN_DEPART) -> TransportOption:
    """A rail option swapped for a real timetabled train (morning for outbound and between, evening for
    home); road and air keep their fixed departure."""
    if option.mode is not Mode.rail:
        return option
    train = evening_train(request, a, b, day, depart) if role == "home" else morning_train(request, a, b, day)
    return train or option


def hop(request: TripRequest, a: str, b: str, day: date, depart: time = HOP_DEPART, role: str = "between") -> Leg | None:
    """The journey from a to b on `day`: TY3's best-ranked option (a real train when that is rail, else
    leaving at `depart`), or a road estimate between the two cities' top places when routes does not know
    a city."""
    found = prefer(_compared(a, b, day, depart, party(request), routes_style(request)), request.transport_mode)
    # Chosen road but routes has no road option: fall through to our own road estimate below. For rail or air
    # there is nothing to estimate, so the best option of any mode stands.
    if found and (request.transport_mode in (None, found[0].mode) or request.transport_mode is not Mode.road):
        return journey(a, b, timed(request, a, b, day, found[0], role, depart), role)
    pa, pb = city_places(request, a), city_places(request, b)
    if not pa or not pb:
        return None
    minutes, cost = Travel().edge(pa[0], pb[0])
    cost *= math.ceil(party(request) / SEATS_PER_CAR)  # a road estimate is per car
    leave = datetime.combine(day, depart)
    return Leg(**{"from": a}, to=b, mode=Mode.road, depart=leave, arrive=leave + timedelta(minutes=minutes),
               minutes=minutes, cost_inr=cost, role=role)


def hops(request: TripRequest, options: list[TransportOption]) -> dict[str, Leg]:
    """The journey into each destination on its first day: from the origin on the chosen transport option
    for the first city, then city to city."""
    split = [(c, d) for c, d in split_days(request) if d]
    out = {}
    if split:
        first, dates = split[0]
        leg = (journey(request.origin, first, options[0], "outbound") if options
               else hop(request, request.origin, first, dates[0], role="outbound"))
        if leg is not None:
            out[first] = leg
    for (prev, _), (city, dates) in zip(split, split[1:]):
        if (leg := hop(request, prev, city, dates[0])) is not None:
            out[city] = leg
    return out


def retime_home(it: Itinerary) -> None:
    """Once the last day is planned: the journey home leaves at least RETURN_BUFFER_MIN after the last visit
    ends (the first train from then on; road leaves then), in the mode of the provisional journey."""
    if not it.days or (out := out_of(it.days[-1])) is None:
        return
    last, lim, travel = it.days[-1], limits(it.request), Travel()
    opened = after_hop(lim, hop_of(last))
    mins = [travel.minutes(x, y) for x, y in zip(last.stops, last.stops[1:])]
    visits, _ = schedule(last.date, last.stops, mins, opened)
    ends = visits[-1].leave if visits else datetime.combine(last.date, opened.start)
    leave = (ends + timedelta(minutes=RETURN_BUFFER_MIN)).time()
    same_mode = it.request.model_copy(update={"transport_mode": out.mode})
    new = hop(same_mode, out.from_, out.to, last.date, leave, role="home")
    if new is None or (new.depart, new.mode) == (out.depart, out.mode):
        return
    if new.mode is not out.mode:
        it.warnings.append(f"No {out.mode.value} home from {out.from_} that day; the journey home is by {new.mode.value}")
    # When even the day's last train leaves before the visits can end, drop visits from the end until it fits.
    stops = list(last.stops)
    while stops and new.depart < _visits_end(last.date, stops, travel, opened) + timedelta(minutes=RETURN_BUFFER_MIN):
        dropped = stops.pop()
        it.warnings.append(f"Dropped {dropped.name} to catch the {new.depart:%H:%M} {new.mode.value} home")
    rebuild_day(it, last.date, stops, travel, lim, out=new)


def _visits_end(day: date, stops: list[Place], travel: Travel, opened) -> datetime:
    mins = [travel.minutes(x, y) for x, y in zip(stops, stops[1:])]
    visits, _ = schedule(day, stops, mins, opened)
    return visits[-1].leave if visits else datetime.combine(day, opened.start)


def home(request: TripRequest) -> Leg | None:
    """The journey back to the origin from the last city: provisional (the solver plans the last day against
    it); retime_home picks the real one once the day's visits are known."""
    split = [(c, d) for c, d in split_days(request) if d]
    if not split:
        return None
    last, dates = split[-1]
    return hop(request, last, request.origin, dates[-1], RETURN_DEPART, role="home")


def city_stays(request: TripRequest, city: str, check_in: date, nights: int) -> list[Stay]:
    """Ranked stays from TY3's routes.stays; sample stays for cities it does not cover."""
    from routes.compare import UnknownPlace
    from routes.stays import rank_stays

    people = max(len(request.constraints.travellers), 1)
    check_out = check_in + timedelta(days=nights)
    try:
        found = rank_stays(city, check_in, check_out, party=people, limit=5, budget_style=routes_style(request))
    except (UnknownPlace, ValueError):
        found = []
    if found or not samples_allowed():
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
        tier="lite", thinking="minimal", label="story",
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
             back: Leg | None, stays_found: list[Stay], transport_reason: str | None = None) -> Itinerary:
    """Solve the days and put the itinerary together with its budget and warnings."""
    days, _ = solve_trip(r, pools, journeys, home=back)
    days = day_titles(days, r)
    empty = [c for c, v in pools.items() if not v]
    it = Itinerary(
        request=r, days=days, lang=r.lang, transport=options, stays=stays_found,
        budget={"transport_inr": 0, "stay_inr": 0, "total_inr": 0},
        # Unused candidates are not a problem (the planner offers more than a trip holds); an empty pool is.
        warnings=[f"No places found yet for {c}" for c in empty]
        + _missing_stays(r, [s.model_dump(mode="json") for s in stays_found]),
        season_notes=season_notes(r),
        transport_reason=transport_reason,
    )
    retime_home(it)
    it.budget = budget(it)
    return it


def season_notes(r: TripRequest) -> list[SeasonNote]:
    """TY2's quoted season notes for each city over the dates the trip spends there: every month it spans,
    each note once, festivals only when their dates fall inside the trip. Nothing when the sources say
    nothing (no guessing)."""
    from guide.season import notes_for_trip

    out: list[SeasonNote] = []
    for city, dates in split_days(r):
        if dates:
            out += [SeasonNote(city=city, text=n["text"], source_url=n["source_url"], kind=n["kind"])
                    for n in notes_for_trip(city, dates[0], dates[-1])]
    return out


def replan(r: TripRequest) -> Itinerary:
    """The whole deterministic plan for a request, without the agents (revise uses it)."""
    options, journeys, back, reason = plan_transport(r)
    pools = {city: city_places(r, city, hours=True) for city in r.destinations}
    return assemble(r, pools, options, journeys, back, stay_options(r), reason)


async def solver(state: dict, model: Model):
    r = _request(state)
    it = assemble(
        r,
        {c: [Place.model_validate(p) for p in v] for c, v in state["pools"].items()},
        [TransportOption.model_validate(t) for t in state["transport"]],
        {c: Leg.model_validate(v) for c, v in state.get("hops", {}).items()},
        Leg.model_validate(state["home"]) if state.get("home") else None,
        [Stay.model_validate(s) for s in state["stays"]],
        state.get("transport_reason"),
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
    it = before.model_copy(deep=True)
    retime_home(it)  # repairs may have shortened the last day
    it = finish(it)  # leftovers (and anything the re-timing broke) become warnings; budget recomputed
    it.days = day_titles(it.days, it.request)  # repairs may have emptied or filled a day
    from .revise import price_options

    await asyncio.to_thread(price_options, it)  # each option's whole-trip total (re-plans per mode)
    left = len(it.warnings) - len(before.warnings)
    return {"itinerary": it.model_dump(mode="json", by_alias=True)}, (f"{left} issue{'s' * (left > 1)} left as warnings" if left else "")


async def narrator(state: dict, model: Model):
    it = _itinerary(state)
    days = "; ".join(f"{d.date:%a %d %b}: {', '.join(p.name for p in d.stops) or 'free day'}" for d in it.days)
    text = await model.text(
        f"In 2 or 3 friendly sentences in {LANG_NAME[it.lang]}, introduce this trip from {it.request.origin} "
        f"to {', '.join(it.request.destinations)}. Days: {days}. Total about ₹{it.budget.total_inr:,}. "
        "Do not add places or prices that are not listed.",
        tier="flash", thinking="low", max_output_tokens=400, label="narrator",
    )
    return {}, text or "Your trip is ready."
