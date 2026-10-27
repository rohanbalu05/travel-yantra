"""Revise a stored plan (card #20): a lighter day, a swapped stop, or a rainy-day re-plan.

Deterministic edits, then the same check-and-repair loop as /plan. No model calls.
"""

from __future__ import annotations

from datetime import date

from ty_contracts import Itinerary, Place, ReviseIntent, ReviseRequest

from . import fakes
from .repair import check_and_repair
from .solver import (
    Limits,
    Travel,
    city_of,
    day_titles,
    fits,
    hop_of,
    limits,
    out_of,
    rebuild_day,
    split_days,
)

# Categories that keep you dry. Everything else (beach, viewpoint, neighbourhood walks, forts) is outdoor.
INDOOR = {"museum", "gallery", "heritage", "temple", "church", "market", "palace", "aquarium", "mall", "food"}


class ReviseError(ValueError):
    """The request does not fit this plan (unknown day or stop). Maps to HTTP 422."""


def candidates(it: Itinerary, city: str | None = None) -> list[Place]:
    """Places the planner could use that this plan does not, for one city (or all): TY2's corpus, then
    the samples."""
    from guide.planner import places_for

    used = {p.id for d in it.days for p in d.stops}
    pool: list[Place] = []
    for c in [city] if city else it.request.destinations:
        one = it.request.model_copy(update={"destinations": [c]})
        pool += [*places_for(c, exclude=frozenset(used)), *fakes.places(one), *fakes.alternatives(one)]
    return [p for p in {p.id: p for p in pool}.values() if p.id not in used]




def _day(it: Itinerary, d: date):
    day = next((x for x in it.days if x.date == d), None)
    if day is None:
        raise ReviseError(f"{d} is not a day of this trip")
    return day


def lighter_day(it: Itinerary, d: date, travel: Travel, lim: Limits) -> str:
    day = _day(it, d)
    if not day.stops:
        return f"{d:%a %d %b} is already free"
    # Take out the longest visit; move it to the lightest day that can take it, else drop it.
    out = max(day.stops, key=lambda p: (p.typical_visit_minutes, p.id))
    rebuild_day(it, d, [p for p in day.stops if p.id != out.id], travel, lim)
    for other in sorted(it.days, key=lambda x: (len(x.stops), x.date)):
        same_city = city_of(it.request, other.date) == city_of(it.request, d)
        if other.date != d and same_city and fits(other.date, [*other.stops, out], travel, lim, hop_of(other), out_of(other)):
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
    near = sorted(candidates(it, city_of(it.request, day.date)),
                  key=lambda p: (p.category != old.category, travel.minutes(old, p), p.id))
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
        spare = [p for p in candidates(it, city_of(it.request, day.date)) if p.category in INDOOR]
        keep = [p for p in day.stops if p.category in INDOOR]
        for old in (p for p in day.stops if p.category not in INDOOR):
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


def revise(it: Itinerary, req: ReviseRequest, travel: Travel | None = None) -> tuple[Itinerary, str, int]:
    """Apply one intent, then check and repair. Returns the plan, what changed, and the repair rounds."""
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
    else:
        what = rain(it, req.day, travel, lim)
    it, rounds = check_and_repair(it, travel)
    it.days = day_titles(it.days, it.request)
    return it, what, rounds


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
