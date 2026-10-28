"""One deterministic repair pass over the checker's violations. The ADK LoopAgent repeats check and repair."""

from __future__ import annotations

from datetime import date

from ty_contracts import DayPlan, Itinerary, Violation, ViolationCode

from .checker import budget, check, chosen_stays, warnings
from .solver import (
    Limits,
    Travel,
    city_of,
    fits,
    hop_of,
    in_area,
    limits,
    out_of,
    rebuild_day,
)

DAY_CODES = (ViolationCode.long_day, ViolationCode.too_much_travel, ViolationCode.no_rest)


def repair(itinerary: Itinerary, violations: list[Violation], travel: Travel | None = None,
           fix_budget: bool = True) -> tuple[Itinerary, list[str]]:
    """Fix what it can. Returns the new itinerary and one line per action taken. Without fix_budget (a
    revise: the traveller already has the plan and chose its stay and way to travel), over budget is left
    as a warning instead of switching their stay or mode."""
    travel = travel or Travel()
    it = itinerary.model_copy(deep=True)
    lim = limits(it.request)
    actions: list[str] = []
    for v in violations:
        if v.code is ViolationCode.budget_mismatch:
            actions.append("Recomputed the budget from its parts")  # it.budget = budget(it) below
        elif v.code is ViolationCode.over_budget:
            actions += _cheaper(it, travel, lim) if fix_budget else []
        elif v.code is ViolationCode.closed and v.place_id:
            actions += _move_or_drop(it, v.day, v.place_id, travel, lim, v.message)
        elif v.code in DAY_CODES and v.day and v.place_id:
            # A stop that cannot be visited that day at all: move it to a day that can take it, else drop it.
            actions += _move_or_drop(it, v.day, v.place_id, travel, lim, v.message)
        elif v.code in DAY_CODES and v.day:
            actions += _lighten(it, v, travel, lim)
    it.budget = budget(it)
    return it, actions


def _day(it: Itinerary, d: date | None) -> DayPlan | None:
    return next((x for x in it.days if x.date == d), None)




def _cheaper_mode(it: Itinerary, travel: Travel) -> list[str]:
    """Over budget on a mode we picked (not one the traveller chose): every journey (out, between cities,
    home) moves to the cheapest other mode, and transport_reason says why."""
    from .accounts import plan_mode
    from .revise import ReviseError, change_transport
    from .steps import MODE_NOUN, retime_home

    used = plan_mode(it)
    if it.request.transport_mode is not None or used is None:
        return []
    firsts: dict = {}
    for o in it.transport:
        firsts.setdefault(o.mode, o)
    now = firsts.get(used)
    cheaper = sorted((o for o in firsts.values() if now and o.total_cost_inr < now.total_cost_inr),
                     key=lambda o: o.total_cost_inr)
    for option in cheaper:
        request = it.request
        try:
            change_transport(it, option.mode, travel)
        except ReviseError:
            continue
        it.request = request  # still the traveller's own request: no mode chosen
        retime_home(it)  # the real train home (and its fare) before the next check
        noun, before = MODE_NOUN[option.mode], MODE_NOUN[used]
        cap = request.constraints.budget_inr or 0
        it.transport_reason = f"{noun.capitalize()}: the {before} would take the trip over your ₹{cap:,} budget."
        return [f"Switched to the {noun} to stay within budget"]
    return []


def _cheaper(it: Itinerary, travel: Travel, lim: Limits) -> list[str]:
    if done := _cheaper_mode(it, travel):
        return done
    first = it.days[0] if it.days else None
    if len(it.transport) > 1 and (first is None or hop_of(first) is None):
        # No journeys in the days (older plans): the budget counts the first option, so put the cheapest first.
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
    # Sights cost little (tickets); dropping them to save money empties the trip. What is left over stays a
    # warning with the total, for the traveller to decide.
    return []


def _move_or_drop(it: Itinerary, d: date | None, place_id: str, travel: Travel, lim: Limits, why: str) -> list[str]:
    day = _day(it, d)
    place = next((p for p in day.stops if p.id == place_id), None) if day else None
    if place is None:
        return []
    rebuild_day(it, day.date, [p for p in day.stops if p.id != place_id], travel, lim)
    for other in sorted(it.days, key=lambda x: len(x.stops)):
        same_city = city_of(it.request, other.date) == city_of(it.request, day.date)
        if other.date != day.date and same_city and in_area(other.stops, place, travel) \
                and fits(other.date, [*other.stops, place], travel, lim, hop_of(other), out_of(other)):
            rebuild_day(it, other.date, [*other.stops, place], travel, lim)
            return [f"Moved {place.name} to {other.date:%a %d %b}"]
    it.warnings.append(f"Dropped {place.name}: {why}")
    return [f"Dropped {place.name}"]


def _lighten(it: Itinerary, v: Violation, travel: Travel, lim: Limits) -> list[str]:
    day = _day(it, v.day)
    if day is None or not day.stops:
        return []
    # First re-plan the day as the solver would (better order, rest breaks). Enough if it now passes.
    rebuild_day(it, day.date, list(day.stops), travel, lim)
    if not [x for x in check(it, travel) if x.day == day.date and x.code in DAY_CODES]:
        return [f"Re-planned {day.date:%a %d %b}"]
    last = _day(it, day.date).stops[-1]
    return _move_or_drop(it, day.date, last.id, travel, lim, v.message)


MAX_ROUNDS = 3


def check_and_repair(itinerary: Itinerary, travel: Travel | None = None, rounds: int = MAX_ROUNDS,
                     fix_budget: bool = True) -> tuple[Itinerary, int]:
    """Plain-Python twin of the ADK loop: check, repair, up to `rounds` times. Leftovers become warnings.
    Returns the itinerary and how many repair rounds ran."""
    travel = travel or Travel()
    it = itinerary
    for n in range(rounds):
        found = check(it, travel)
        if not fix_budget:
            found = [v for v in found if v.code is not ViolationCode.over_budget]
        if not found:
            return it, n
        it, _ = repair(it, found, travel, fix_budget)
    return finish(it, travel), rounds


def finish(itinerary: Itinerary, travel: Travel | None = None) -> Itinerary:
    """After the last round: anything still wrong goes into warnings; budget is recomputed."""
    it = itinerary.model_copy(deep=True)
    it.budget = budget(it)
    it.warnings += [w for w in warnings(check(it, travel)) if w not in it.warnings]
    return it
