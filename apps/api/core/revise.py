"""Revise a stored plan (card #20): a lighter day, a swapped stop, or a rainy-day re-plan.

Deterministic edits, then the same check-and-repair loop as /plan. No model calls.
"""

from __future__ import annotations

import difflib
import math
import re
from datetime import date

from ty_contracts import Itinerary, Mode, Place, ReviseIntent, ReviseRequest

from . import fakes
from .repair import check_and_repair
from .solver import (
    _KEEP,
    Limits,
    Travel,
    city_of,
    day_titles,
    fits,
    hop_of,
    in_area,
    limits,
    out_of,
    rebuild_day,
    split_days,
)

# Categories that keep you dry, for places outside TY2's corpus (samples); corpus places use TY2's
# guide.planner.is_indoor (palace interiors yes, Hampi's open temples no). Food stops, markets, beaches,
# viewpoints, forts and walks are not a rain plan.
INDOOR = {"museum", "gallery", "heritage", "temple", "church", "palace", "aquarium"}
# A swap never lands on the same site: within this distance, or sharing a distinctive name
# (Chamundeshwari Temple and Chamundi Hills).
SAME_SITE_KM = 1.0
GENERIC_WORDS = {"temple", "palace", "museum", "church", "beach", "market", "garden", "gardens", "statue", "hills",
                 "falls", "lake", "fort", "cathedral", "basilica", "gallery", "viewpoint", "national", "sunset",
                 "street", "quarter", "latin", "india", "state", "sweet", "zoological"}
LOW = 10_000  # rank of a place the planner does not list


def indoor(p: Place) -> bool:
    from guide.planner import SOURCE, is_indoor

    return is_indoor(p) if p.source == SOURCE else p.category in INDOOR


def _km(a: Place, b: Place) -> float:
    dlat, dlng = math.radians(b.lat - a.lat), math.radians(b.lng - a.lng)
    h = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a.lat)) * math.cos(math.radians(b.lat)) * math.sin(dlng / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _stems(name: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[a-z]+", name.lower()) if len(w) >= 5 and w not in GENERIC_WORDS}


def same_site(a: Place, b: Place) -> bool:
    return _km(a, b) < SAME_SITE_KM or bool(_stems(a.name) & _stems(b.name))


def _name(p: Place) -> str:
    return re.sub(r"[^a-z0-9]+", " ", p.name.lower()).strip()


def ranks(it: Itinerary, city: str) -> dict[str, int]:
    """The planner's order for a city (0 is its top sight); samples after it in tests."""
    from guide.planner import places_for

    from .steps import samples_allowed

    order = places_for(city)
    if samples_allowed():
        order += fakes.places(it.request.model_copy(update={"destinations": [city]}))
    out: dict[str, int] = {}
    for i, p in enumerate(order):
        out.setdefault(p.id, i)
    return out


class ReviseError(ValueError):
    """The request does not fit this plan (unknown day or stop). Maps to HTTP 422."""


def candidates(it: Itinerary, city: str | None = None) -> list[Place]:
    """Places the planner could use that this plan does not, for one city (or all): TY2's corpus, then
    the samples."""
    from guide.hours import live_hours
    from guide.planner import places_for

    from .steps import samples_allowed

    used = {p.id for d in it.days for p in d.stops}
    pool: list[Place] = []
    for c in [city] if city else it.request.destinations:
        one = it.request.model_copy(update={"destinations": [c]})
        # Revise runs in a worker thread, so live_hours (Places, cached) may call the network here.
        pool += live_hours(places_for(c, exclude=frozenset(used)))
        if samples_allowed():
            pool += [*fakes.places(one), *fakes.alternatives(one)]
    # Never the same place again under another id (a sample and a corpus copy of one basilica).
    names = {_name(p) for d in it.days for p in d.stops}
    return [p for p in {p.id: p for p in pool}.values() if p.id not in used and _name(p) not in names]




def _day(it: Itinerary, d: date):
    day = next((x for x in it.days if x.date == d), None)
    if day is None:
        raise ReviseError(f"{d} is not a day of this trip")
    return day


def lighter_day(it: Itinerary, d: date, travel: Travel, lim: Limits) -> str:
    day = _day(it, d)
    if not day.stops:
        return f"{d:%a %d %b} is already free"
    rank = ranks(it, city_of(it.request, d) or it.request.destinations[0])
    if len(day.stops) == 1:
        return f"{d:%a %d %b} has only {day.stops[0].name} left; nothing taken out"
    # Take out the lowest-priority stop (never the day's top sight); move it to the lightest day that can
    # take it, else drop it.
    top = min(day.stops, key=lambda p: (rank.get(p.id, LOW), p.id))
    out = max((p for p in day.stops if p.id != top.id),
              key=lambda p: (rank.get(p.id, LOW), p.typical_visit_minutes, p.id))
    rebuild_day(it, d, [p for p in day.stops if p.id != out.id], travel, lim)
    for other in sorted(it.days, key=lambda x: (len(x.stops), x.date)):
        same_city = city_of(it.request, other.date) == city_of(it.request, d)
        if other.date != d and same_city and in_area(other.stops, out, travel) \
                and fits(other.date, [*other.stops, out], travel, lim, hop_of(other), out_of(other)):
            rebuild_day(it, other.date, [*other.stops, out], travel, lim)
            return f"Moved {out.name} to {other.date:%a %d %b}"
    it.warnings.append(f"Dropped {out.name} to make {d:%a %d %b} lighter")
    return f"Dropped {out.name}"


def swap_stop(it: Itinerary, place_id: str, travel: Travel, lim: Limits) -> str:
    day = next((d for d in it.days if any(p.id == place_id for p in d.stops)), None)
    if day is None:
        raise ReviseError(f"{place_id} is not in this plan")
    old = next(p for p in day.stops if p.id == place_id)
    keep = [p for p in day.stops if p.id != place_id]
    # Not the same site again (within ~1 km, or Chamundeshwari Temple for Chamundi Hills), nor a stop's twin.
    pool = [p for p in candidates(it, city_of(it.request, day.date)) if not any(same_site(p, q) for q in [old, *keep])]
    near = sorted(pool, key=lambda p: (p.category != old.category, travel.minutes(old, p), p.id))
    new = next((p for p in near if fits(day.date, [*keep, p], travel, lim, hop_of(day), out_of(day))), None)
    rebuild_day(it, day.date, [*keep, new] if new else keep, travel, lim)
    if new is None:
        it.warnings.append(f"No other place fits {day.date:%a %d %b}; removed {old.name}")
        return f"Removed {old.name}"
    return f"Swapped {old.name} for {new.name}"


def rain(it: Itinerary, d: date | None, travel: Travel, lim: Limits) -> str:
    days = [_day(it, d)] if d else list(it.days)
    changes = []
    for day in days:
        spare = [p for p in candidates(it, city_of(it.request, day.date)) if indoor(p)]
        keep = [p for p in day.stops if indoor(p)]
        for old in (p for p in day.stops if not indoor(p)):
            pick = min(spare, key=lambda p: (travel.minutes(old, p), p.id), default=None)
            if pick and fits(day.date, [*keep, pick], travel, lim, hop_of(day), out_of(day)):
                spare.remove(pick)
                keep.append(pick)
                changes.append(f"{old.name} → {pick.name}")
            else:
                it.warnings.append(f"Rain: dropped {old.name} on {day.date:%a %d %b}; no indoor place fits")
                changes.append(f"dropped {old.name}")
        rebuild_day(it, day.date, keep, travel, lim)
    return "Rain plan: " + ("; ".join(changes) if changes else "every stop is already indoors")


def find_place(it: Itinerary, text: str | None, place_id: str | None) -> tuple[Place, str]:
    """A place the traveller names ("Fort Aguada") or a planner id, among the trip's cities: the place and
    its city. ReviseError when none matches."""
    from guide.hours import live_hours
    from guide.planner import places_for

    from .steps import samples_allowed

    pool: list[tuple[Place, str]] = []
    for c in it.request.destinations:
        found = places_for(c)
        if samples_allowed():
            one = it.request.model_copy(update={"destinations": [c]})
            found += [*fakes.places(one), *fakes.alternatives(one)]
        pool += [(p, c) for p in found]
    wanted = (place_id or text or "").strip()
    hit = next(((p, c) for p, c in pool if p.id == wanted), None)
    if hit is None and text:
        key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        names = {_name(p): (p, c) for p, c in reversed(pool)}
        hit = names.get(key) or next((names[n] for n in names if key and (n.startswith(key) or key in n)), None)
        if hit is None and (close := difflib.get_close_matches(key, list(names), n=1, cutoff=0.75)):
            hit = names[close[0]]
    if hit is None:
        raise ReviseError(f"I could not find {wanted} in {', '.join(it.request.destinations)}")
    place, city = hit
    return live_hours([place])[0], city


def _where(it: Itinerary, place_id: str):
    return next((d for d in it.days if any(p.id == place_id for p in d.stops)), None)


def _relocate(it: Itinerary, p: Place, away_from: date, travel: Travel, lim: Limits, why: str) -> str:
    """Put a stop that had to leave a day on another day of its city in the same area, else drop it."""
    for other in sorted(it.days, key=lambda x: (len(x.stops), x.date)):
        if other.date != away_from and city_of(it.request, other.date) == city_of(it.request, away_from) \
                and in_area(other.stops, p, travel) \
                and fits(other.date, [*other.stops, p], travel, lim, hop_of(other), out_of(other)):
            rebuild_day(it, other.date, [*other.stops, p], travel, lim)
            return f"moved {p.name} to {other.date:%a %d %b}"
    it.warnings.append(f"Dropped {p.name} {why}")
    return f"dropped {p.name}"


def place_on(it: Itinerary, place: Place, city: str, day: date | None, travel: Travel, lim: Limits,
             verb: str = "Added") -> str:
    """Put a place on the given day (or the best day of its city: one in its area with room, the emptiest
    first). When the day is full, its lowest-priority stops make room and go to another day or are dropped."""
    days = [d for d in it.days if city_of(it.request, d.date) == city]
    if day is not None:
        target = _day(it, day)
        if city_of(it.request, day) != city:
            raise ReviseError(f"{place.name} is in {city}; {day:%a %d %b} is a "
                              f"{city_of(it.request, day)} day")
        days = [target]
    if not days:
        raise ReviseError(f"this trip has no day in {city}")
    days.sort(key=lambda d: (not in_area(d.stops, place, travel), len(d.stops), d.date))
    for d in days:
        if fits(d.date, [*d.stops, place], travel, lim, hop_of(d), out_of(d)):
            rebuild_day(it, d.date, [*d.stops, place], travel, lim)
            return f"{verb} {place.name} to {d.date:%a %d %b}"
    target = days[0]
    if not fits(target.date, [place], travel, lim, hop_of(target), out_of(target)):
        raise ReviseError(f"{place.name} does not fit {target.date:%a %d %b} (opening hours or the journey that day)")
    rank = ranks(it, city)
    stops, out = list(target.stops), []
    top = min(stops, key=lambda p: (rank.get(p.id, LOW), p.id), default=None)
    while stops and not fits(target.date, [*stops, place], travel, lim, hop_of(target), out_of(target)):
        lowest = max(stops, key=lambda p: (rank.get(p.id, LOW), p.typical_visit_minutes, p.id))
        if lowest is top and rank.get(top.id, LOW) < rank.get(place.id, LOW):
            # Making room would take out the day's top sight: say where it fits instead.
            free = next((d for d in it.days if city_of(it.request, d.date) == city and d.date != target.date
                         and fits(d.date, [*d.stops, place], travel, lim, hop_of(d), out_of(d))), None)
            hint = f"; it fits on {free.date:%a %d %b}" if free else ""
            raise ReviseError(f"{target.date:%a %d %b} is full with {top.name}{hint}")
        stops.remove(lowest)
        out.append(lowest)
    rebuild_day(it, target.date, [*stops, place], travel, lim)
    moved = [_relocate(it, p, target.date, travel, lim, f"to make room for {place.name}") for p in out]
    return f"{verb} {place.name} to {target.date:%a %d %b}" + (f" ({'; '.join(moved)})" if moved else "")


def add_stop(it: Itinerary, req: ReviseRequest, travel: Travel, lim: Limits) -> str:
    place, city = find_place(it, req.place, req.place_id)
    if (day := _where(it, place.id)) is not None or any(_name(p) == _name(place) for d in it.days for p in d.stops):
        on = day or next(d for d in it.days if any(_name(p) == _name(place) for p in d.stops))
        raise ReviseError(f"{place.name} is already on {on.date:%a %d %b}")
    return place_on(it, place, city, req.day, travel, lim)


def remove_stop(it: Itinerary, place_id: str, travel: Travel, lim: Limits) -> str:
    day = _where(it, place_id)
    if day is None:
        raise ReviseError(f"{place_id} is not in this plan")
    gone = next(p for p in day.stops if p.id == place_id)
    rebuild_day(it, day.date, [p for p in day.stops if p.id != place_id], travel, lim)
    return f"Removed {gone.name} from {day.date:%a %d %b}"


def move_stop(it: Itinerary, place_id: str, to: date, travel: Travel, lim: Limits) -> str:
    day = _where(it, place_id)
    if day is None:
        raise ReviseError(f"{place_id} is not in this plan")
    target = _day(it, to)
    place = next(p for p in day.stops if p.id == place_id)
    if target.date == day.date:
        return f"{place.name} is already on {to:%a %d %b}"
    city = city_of(it.request, day.date)
    if city_of(it.request, to) != city:
        raise ReviseError(f"{place.name} is in {city}; {to:%a %d %b} is a {city_of(it.request, to)} day")
    rebuild_day(it, day.date, [p for p in day.stops if p.id != place_id], travel, lim)
    return place_on(it, place, city, to, travel, lim, verb="Moved")


def revise(it: Itinerary, req: ReviseRequest, travel: Travel | None = None,
           priced: bool = True) -> tuple[Itinerary, str, int]:
    """Apply one intent, then check and repair. Returns the plan, what changed, and the repair rounds.
    With `priced`, each transport option also gets its whole-trip total (price_options)."""
    travel = travel or Travel()
    it = it.model_copy(deep=True)
    if req.lang:
        it.lang = req.lang
    lim = limits(it.request)
    if req.intent is ReviseIntent.lighter_day:
        what = lighter_day(it, req.day, travel, lim)
    elif req.intent is ReviseIntent.swap_stop:
        what = swap_stop(it, req.place_id, travel, lim)
    elif req.intent is ReviseIntent.move_day:
        it, what = move_day(it, req.city)
    elif req.intent is ReviseIntent.transport:
        what = change_transport(it, req.mode, travel)
    elif req.intent is ReviseIntent.rain:
        what = rain(it, req.day, travel, lim)
    elif req.intent is ReviseIntent.add_stop:
        what = add_stop(it, req, travel, lim)
    elif req.intent is ReviseIntent.remove_stop:
        what = remove_stop(it, req.place_id, travel, lim)
    elif req.intent is ReviseIntent.move_stop:
        what = move_stop(it, req.place_id, req.day, travel, lim)
    else:
        raise ReviseError(f"{req.intent.value}: this change is not available yet")
    from .repair import finish
    from .steps import retime_home

    retime_home(it)  # new journeys or stops on the last day: the real train home before checking
    it, rounds = check_and_repair(it, travel)
    retime_home(it)  # repairs may have shortened the last day
    it = finish(it, travel)  # anything the re-timing broke (the budget) becomes a warning
    it.days = day_titles(it.days, it.request)
    if priced:
        price_options(it)
    return it, what, rounds


def price_options(it: Itinerary) -> Itinerary:
    """Set TransportOption.trip_total_inr on every option: the option in use is the plan's own total; the
    first option of another mode is the total the transport revise to that mode gives (so the number shown
    before switching is the number after); another option of a mode is that mode's total with this option's
    fare instead. A mode the revise cannot switch to gets None."""
    from .accounts import plan_mode

    used = plan_mode(it)
    totals: dict = {}
    firsts = {}
    for o in it.transport:
        firsts.setdefault(o.mode, o)
    for mode, first in firsts.items():
        if mode is used:
            totals[mode] = it.budget.total_inr
            continue
        try:
            switched, _, _ = revise(it, ReviseRequest(intent=ReviseIntent.transport, mode=mode), priced=False)
        except ReviseError:
            continue
        totals[mode] = switched.budget.total_inr
    for o in it.transport:
        base, first = totals.get(o.mode), firsts[o.mode]
        o.trip_total_inr = None if base is None else max(base - first.total_cost_inr + o.total_cost_inr, 0)
    return it


def move_day(it: Itinerary, city: str) -> tuple[Itinerary, str]:
    """Give `city` one more day, taken from the neighbouring city (in trip order) that has more days, the
    earlier one on a tie and never its last day; then re-plan the trip around the new split."""
    from .steps import replan

    req = it.request
    names = [d.lower() for d in req.destinations]
    if city.lower() not in names:
        raise ReviseError(f"{city} is not a destination of this trip")
    if len(names) < 2:
        raise ReviseError("move_day needs a trip with more than one destination")
    i = names.index(city.lower())
    counts = [len(dates) for _, dates in split_days(req)]
    donors = [j for j in (i - 1, i + 1) if 0 <= j < len(counts) and counts[j] > 1]
    if not donors:
        raise ReviseError(f"no city next to {req.destinations[i]} has a day to spare")
    donor = max(donors, key=lambda j: (counts[j], -j))
    counts[donor] -= 1
    counts[i] += 1
    moved = replan(req.model_copy(update={"days_per_destination": counts}))
    moved.lang = it.lang
    # A new split re-plans every day, so earlier swaps, rain plans and lighter days do not carry over.
    moved.warnings.append("The days were re-planned for the new split; earlier changes to this plan were replaced.")
    return moved, f"Moved a day from {req.destinations[donor]} to {req.destinations[i]}"


def change_transport(it: Itinerary, mode: Mode, travel: Travel) -> str:
    """Every journey (out, between cities, home) switches to `mode`; each day keeps its stops and is re-timed
    around its new journeys."""
    from .steps import chosen_options, home, hops

    req = it.request.model_copy(update={"transport_mode": mode})
    options = chosen_options(req)
    if not options or options[0].mode is not mode:
        raise ReviseError(f"there is no {mode.value} option for this trip")
    it.request, it.transport = req, options
    it.transport_reason = None  # the traveller chose
    lim = limits(req)
    starts = {dates[0]: city for city, dates in split_days(req) if dates}
    journeys, back = hops(req, options), home(req)
    last = it.days[-1].date if it.days else None
    for day in list(it.days):
        new_hop = journeys.get(starts[day.date]) if day.date in starts else _KEEP
        new_out = back if day.date == last else _KEEP
        if new_hop is not _KEEP or new_out is not _KEEP:
            rebuild_day(it, day.date, list(day.stops), travel, lim, hop=new_hop, out=new_out)
    word = {"rail": "train", "road": "road", "air": "air"}[mode.value]
    # Between some cities the chosen mode may not exist; say so rather than claim every journey switched.
    kept = [leg for leg in [*journeys.values(), back] if leg and leg.mode is not mode]
    for leg in kept:
        it.warnings.append(f"No {word} between {leg.from_} and {leg.to}; that journey stays by {leg.mode.value}")
    return f"Switched every journey to {word}" if not kept else f"Switched journeys to {word} where possible"
