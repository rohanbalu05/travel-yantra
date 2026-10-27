"""Revise a stored plan (card #20): a lighter day, a swapped stop, or a rainy-day re-plan.

Deterministic edits, then the same check-and-repair loop as /plan. No model calls.
"""

from __future__ import annotations

from datetime import date

from ty_contracts import Itinerary, Place, ReviseIntent, ReviseRequest

from . import fakes
from .repair import check_and_repair
from .solver import Limits, Travel, build_day, fits, limits

# Categories that keep you dry. Everything else (beach, viewpoint, neighbourhood walks, forts) is outdoor.
INDOOR = {"museum", "gallery", "heritage", "temple", "church", "market", "palace", "aquarium", "mall", "food"}


class ReviseError(ValueError):
    """The request does not fit this plan (unknown day or stop). Maps to HTTP 422."""


def candidates(it: Itinerary) -> list[Place]:
    """Places the planner could use that this plan does not: TY2's corpus, then the samples."""
    from guide.planner import places_for

    used = {p.id for d in it.days for p in d.stops}
    corpus = [p for city in it.request.destinations for p in places_for(city, exclude=frozenset(used))]
    pool = [*corpus, *fakes.places(it.request), *fakes.alternatives(it.request)]
    return [p for p in {p.id: p for p in pool}.values() if p.id not in used]


def _rebuild(it: Itinerary, d: date, stops: list[Place], travel: Travel, lim: Limits) -> None:
    i = next(i for i, x in enumerate(it.days) if x.date == d)
    it.days[i] = build_day(d, stops, travel, lim)[0].model_copy(update={"notes": it.days[i].notes})


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
    _rebuild(it, d, [p for p in day.stops if p.id != out.id], travel, lim)
    for other in sorted(it.days, key=lambda x: (len(x.stops), x.date)):
        if other.date != d and fits(other.date, [*other.stops, out], travel, lim):
            _rebuild(it, other.date, [*other.stops, out], travel, lim)
            return f"Moved {out.name} to {other.date:%a %d %b}"
    it.warnings.append(f"Dropped {out.name} to make {d:%a %d %b} lighter")
    return f"Dropped {out.name}"


def swap_stop(it: Itinerary, place_id: str, travel: Travel, lim: Limits) -> str:
    day = next((d for d in it.days if any(p.id == place_id for p in d.stops)), None)
    if day is None:
        raise ReviseError(f"{place_id} is not in this plan")
    old = next(p for p in day.stops if p.id == place_id)
    keep = [p for p in day.stops if p.id != place_id]
    near = sorted(candidates(it), key=lambda p: (p.category != old.category, travel.minutes(old, p), p.id))
    new = next((p for p in near if fits(day.date, [*keep, p], travel, lim)), None)
    _rebuild(it, day.date, [*keep, new] if new else keep, travel, lim)
    if new is None:
        it.warnings.append(f"No other place fits {day.date:%a %d %b}; removed {old.name}")
        return f"Removed {old.name}"
    return f"Swapped {old.name} for {new.name}"


def rain(it: Itinerary, d: date | None, travel: Travel, lim: Limits) -> str:
    days = [_day(it, d)] if d else list(it.days)
    spare = [p for p in candidates(it) if p.category in INDOOR]
    changes = []
    for day in days:
        keep = [p for p in day.stops if p.category in INDOOR]
        for old in (p for p in day.stops if p.category not in INDOOR):
            pick = min(spare, key=lambda p: (travel.minutes(old, p), p.id), default=None)
            if pick and fits(day.date, [*keep, pick], travel, lim):
                spare.remove(pick)
                keep.append(pick)
                changes.append(f"{old.name} → {pick.name}")
            else:
                it.warnings.append(f"Rain: dropped {old.name} on {day.date:%a %d %b}; no indoor place fits")
                changes.append(f"dropped {old.name}")
        _rebuild(it, day.date, keep, travel, lim)
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
    else:
        what = rain(it, req.day, travel, lim)
    it, rounds = check_and_repair(it, travel)
    return it, what, rounds
