"""Deterministic checks on an Itinerary. Returns typed Violations; no model calls."""

from __future__ import annotations

from datetime import datetime, timedelta

from ty_contracts import BudgetSummary, Itinerary, Stay, Violation, ViolationCode

from .solver import (
    ELDERLY_AGE,
    REST_NOTE,
    RETURN_BUFFER_MIN,
    Limits,
    Travel,
    after_hop,
    hop_of,
    hours_on,
    limits,
    out_of,
    stop_legs,
)

# Estimates (reversible): the sample budgets use these, so the Goa sample totals ₹46,800.
ACTIVITY_INR_PER_STOP_PERSON = 150
FOOD_INR_PER_DAY_PERSON = 750
LONG_DAY_HOURS = 10
# Elderly travellers: more than this many hours out without a break is a no_rest violation.
ELDERLY_MAX_OUT_HOURS = 6


def chosen_stays(itinerary: Itinerary) -> list[Stay]:
    """The first stay listed for each check-in date (one per city on a multi-city trip)."""
    return list({s.check_in: s for s in reversed(itinerary.stays)}.values())[::-1]


def budget(itinerary: Itinerary) -> BudgetSummary:
    """Transport is every journey in the plan (out, between cities, home), per traveller; a plan without an
    outbound journey on day 1 counts the first transport option instead. Stays are the chosen stay per city,
    priced for the whole party per night."""
    people = max(len(itinerary.request.constraints.travellers), 1)
    journeys = [leg for d in itinerary.days for leg in (hop_of(d), out_of(d)) if leg]
    transport = sum(leg.cost_inr for leg in journeys) * people
    first = itinerary.days[0] if itinerary.days else None
    hop = hop_of(first) if first is not None else None
    # role "outbound", or (plans saved before Leg.role) a day-1 journey from the origin
    outbound = hop is not None and (hop.role == "outbound" or (hop.role is None and hop.from_ == itinerary.request.origin))
    if not outbound and itinerary.transport:
        transport += itinerary.transport[0].total_cost_inr * people
    stay = sum(s.price_per_night_inr * max((s.check_out - s.check_in).days, 1) for s in chosen_stays(itinerary))
    stops = sum(len(d.stops) for d in itinerary.days)
    activities = ACTIVITY_INR_PER_STOP_PERSON * stops * people
    food = FOOD_INR_PER_DAY_PERSON * len(itinerary.days) * people
    total = transport + stay + activities + food
    cap = itinerary.request.constraints.budget_inr
    return BudgetSummary(transport_inr=transport, stay_inr=stay, activities_inr=activities, food_inr=food,
                         total_inr=total, within_budget=None if cap is None else total <= cap)


def check(itinerary: Itinerary, travel: Travel | None = None) -> list[Violation]:
    travel = travel or Travel()
    req = itinerary.request
    lim = limits(req)
    out: list[Violation] = []

    b = budget(itinerary)
    if b.within_budget is False:
        out.append(Violation(code=ViolationCode.over_budget,
                             message=f"Total ₹{b.total_inr:,} is over the ₹{req.constraints.budget_inr:,} budget"))

    elderly = any(t.age >= ELDERLY_AGE for t in req.constraints.travellers)
    for day in itinerary.days:
        out += _check_day(day, lim, elderly, travel)
    return out


def _check_day(day, lim: Limits, elderly: bool, travel: Travel) -> list[Violation]:
    if not day.stops:
        return []
    out: list[Violation] = []
    # A journey may open the day (visits start after it) or close it (visits end before it). Only local
    # road time counts against the daily cap.
    hop, home = hop_of(day), out_of(day)
    # A long day is about time out and about: from arrival, not from boarding the train.
    begin = datetime.combine(day.date, lim.start) if hop is None else hop.arrive
    # Travel times come from the plan's own legs when they line up with the stops, else from the provider.
    leg_min = [leg.minutes for leg in stop_legs(day)]
    transfer = next((leg for leg in day.legs if leg.role == "transfer"), None)
    if len(leg_min) != len(day.stops) - 1:
        leg_min = [travel.minutes(a, b) for a, b in zip(day.stops, day.stops[1:])]

    # Replay the day from its start with no end-of-day cut-off, so lateness is reported once, as long_day.
    t = datetime.combine(day.date, after_hop(lim, hop).start)
    if transfer and transfer.arrive > t:  # visits start once the ride from the station arrives
        t = transfer.arrive
    first_start = last_leave = None
    for i, p in enumerate(day.stops):
        if i:
            t += timedelta(minutes=leg_min[i - 1])
        window = hours_on(p, day.date)
        if window is None:
            out.append(Violation(code=ViolationCode.closed, day=day.date, place_id=p.id,
                                 message=f"{p.name} is closed that day"))
            continue
        opens, closes = (datetime.combine(day.date, w) for w in window)
        start = max(t, opens)
        leave = start + timedelta(minutes=p.typical_visit_minutes)
        if leave > closes:
            out.append(Violation(code=ViolationCode.closed, day=day.date, place_id=p.id,
                                 message=f"{p.name} closes at {window[1]:%H:%M} before the visit ends"))
        first_start = first_start or start
        last_leave, t = leave, leave

    missed_home = bool(last_leave and home and last_leave > home.depart - timedelta(minutes=RETURN_BUFFER_MIN))
    if missed_home:
        out.append(Violation(code=ViolationCode.long_day, day=day.date,
                             message=f"Visits run past {home.depart:%H:%M}, when the {home.mode.value} home leaves"))
    if first_start and last_leave:
        hours = (last_leave - begin).total_seconds() / 3600
        if hours > LONG_DAY_HOURS and not missed_home:  # one long_day per day is enough
            out.append(Violation(code=ViolationCode.long_day, day=day.date,
                                 message=f"{hours:.1f}-hour day; keep it under {LONG_DAY_HOURS}"))
        elif elderly and hours > ELDERLY_MAX_OUT_HOURS and REST_NOTE not in day.notes:
            out.append(Violation(code=ViolationCode.no_rest, day=day.date,
                                 message=f"{hours:.1f} hours out with no rest for elderly travellers"))

    road = sum(leg_min) + (transfer.minutes if transfer else 0)
    if road > lim.max_travel_min:
        out.append(Violation(code=ViolationCode.too_much_travel, day=day.date,
                             message=f"{road} min on the road; the limit is {lim.max_travel_min}"))
    return out


def warnings(violations: list[Violation]) -> list[str]:
    return [v.message if v.day is None else f"{v.day:%a %d %b}: {v.message}" for v in violations]
