"""One deterministic repair pass over the checker's violations. The ADK LoopAgent repeats check and repair."""

from __future__ import annotations

from datetime import date

from ty_contracts import DayPlan, Itinerary, Place, Violation, ViolationCode

from .checker import budget, check, chosen_stays, warnings
from .solver import (
    HOP_NOTE,
    REST_NOTE,
    Limits,
    Travel,
    build_day,
    city_of,
    fits,
    hop_of,
    limits,
)

DAY_CODES = (ViolationCode.long_day, ViolationCode.too_much_travel, ViolationCode.no_rest)


def repair(itinerary: Itinerary, violations: list[Violation], travel: Travel | None = None) -> tuple[Itinerary, list[str]]:
    """Fix what it can. Returns the new itinerary and one line per action taken."""
    travel = travel or Travel()
    it = itinerary.model_copy(deep=True)
    lim = limits(it.request)
    actions: list[str] = []
    for v in violations:
        if v.code is ViolationCode.over_budget:
            actions += _cheaper(it, travel, lim)
        elif v.code is ViolationCode.closed and v.place_id:
            actions += _move_or_drop(it, v.day, v.place_id, travel, lim, v.message)
        elif v.code in DAY_CODES and v.day:
            actions += _lighten(it, v, travel, lim)
    it.budget = budget(it)
    return it, actions


def _day(it: Itinerary, d: date | None) -> DayPlan | None:
    return next((x for x in it.days if x.date == d), None)


def _rebuild(it: Itinerary, d: date, stops: list[Place], travel: Travel, lim: Limits) -> None:
    i = next(i for i, x in enumerate(it.days) if x.date == d)
    plan, _ = build_day(d, stops, travel, lim, hop=hop_of(it.days[i]))
    # Keep the day's own notes; the rest and travel notes are rebuilt with the day.
    plan.notes = [n for n in it.days[i].notes if n != REST_NOTE and not n.startswith(HOP_NOTE)] + plan.notes
    it.days[i] = plan


def _cheaper(it: Itinerary, travel: Travel, lim: Limits) -> list[str]:
    if len(it.transport) > 1:
        cheapest = min(it.transport, key=lambda o: o.total_cost_inr)
        if cheapest is not it.transport[0] and cheapest.total_cost_inr < it.transport[0].total_cost_inr:
            it.transport.remove(cheapest)
            it.transport.insert(0, cheapest)
            return [f"Switched to {cheapest.mode.value} to save money"]
    for chosen in chosen_stays(it):
        same = [s for s in it.stays if s.check_in == chosen.check_in]
        cheaper = min(same, key=lambda s: s.price_per_night_inr)
        if cheaper.price_per_night_inr < chosen.price_per_night_inr:
            # Put the cheaper one first for that check-in, so it becomes the chosen stay.
            it.stays.remove(cheaper)
            it.stays.insert(it.stays.index(chosen), cheaper)
            return [f"Switched to {cheaper.name} to save money"]
    fullest = max(it.days, key=lambda d: len(d.stops))
    if not fullest.stops:
        return []
    drop = max(fullest.stops, key=lambda p: p.typical_visit_minutes)
    _rebuild(it, fullest.date, [p for p in fullest.stops if p.id != drop.id], travel, lim)
    it.warnings.append(f"Dropped {drop.name} to stay within budget")
    return [f"Dropped {drop.name} to save money"]


def _move_or_drop(it: Itinerary, d: date | None, place_id: str, travel: Travel, lim: Limits, why: str) -> list[str]:
    day = _day(it, d)
    place = next((p for p in day.stops if p.id == place_id), None) if day else None
    if place is None:
        return []
    _rebuild(it, day.date, [p for p in day.stops if p.id != place_id], travel, lim)
    for other in sorted(it.days, key=lambda x: len(x.stops)):
        same_city = city_of(it.request, other.date) == city_of(it.request, day.date)
        if other.date != day.date and same_city and fits(other.date, [*other.stops, place], travel, lim, hop_of(other)):
            _rebuild(it, other.date, [*other.stops, place], travel, lim)
            return [f"Moved {place.name} to {other.date:%a %d %b}"]
    it.warnings.append(f"Dropped {place.name}: {why}")
    return [f"Dropped {place.name}"]


def _lighten(it: Itinerary, v: Violation, travel: Travel, lim: Limits) -> list[str]:
    day = _day(it, v.day)
    if day is None or not day.stops:
        return []
    # First re-plan the day as the solver would (better order, rest breaks). Enough if it now passes.
    _rebuild(it, day.date, list(day.stops), travel, lim)
    if not [x for x in check(it, travel) if x.day == day.date and x.code in DAY_CODES]:
        return [f"Re-planned {day.date:%a %d %b}"]
    last = _day(it, day.date).stops[-1]
    return _move_or_drop(it, day.date, last.id, travel, lim, v.message)


MAX_ROUNDS = 3


def check_and_repair(itinerary: Itinerary, travel: Travel | None = None, rounds: int = MAX_ROUNDS) -> tuple[Itinerary, int]:
    """Plain-Python twin of the ADK loop: check, repair, up to `rounds` times. Leftovers become warnings.
    Returns the itinerary and how many repair rounds ran."""
    travel = travel or Travel()
    it = itinerary
    for n in range(rounds):
        found = check(it, travel)
        if not found:
            return it, n
        it, _ = repair(it, found, travel)
    return finish(it, travel), rounds


def finish(itinerary: Itinerary, travel: Travel | None = None) -> Itinerary:
    """After the last round: anything still wrong goes into warnings; budget is recomputed."""
    it = itinerary.model_copy(deep=True)
    it.budget = budget(it)
    it.warnings += [w for w in warnings(check(it, travel)) if w not in it.warnings]
    return it
