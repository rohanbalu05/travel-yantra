"""Deterministic day solver: cluster places into days, order each day, schedule within opening hours.

No model calls. Travel times come from TY3's RoadEdgeProvider (HaversineRoadProvider offline).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from functools import lru_cache

from routes.graph import KIND_PLACE, HaversineRoadProvider, Node, RoadEdgeProvider
from ty_contracts import (
    DayPlan,
    Itinerary,
    Leg,
    Mode,
    Pace,
    Place,
    StopTime,
    TransportOption,
    TripRequest,
)

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# Road costs (cabs, a car) are per vehicle; a party needs one per this many people.
SEATS_PER_CAR = 4
ELDERLY_AGE = 60
# Elderly travellers get a rest break before the next stop once they have been out this long.
REST_AFTER_MIN = 180
REST_MIN = 45
REST_NOTE = "Rest break"
# When filling a day, each step down the planner's ranking counts as this many minutes of extra travel.
RANK_MINUTES = 6
# A travel day: the note that names the hop, and the time to settle in after arriving.
HOP_NOTE = "Travel: "
HOP_SETTLE_MIN = 30
# After a journey arrives: the wait before the ride to the first stop.
TRANSFER_WAIT_MIN = 10
# The journey home: its note, the default departure time and how long before it the last visit ends.
RETURN_NOTE = "Return: "
# The last day is planned to about RETURN_FILL_END; the journey home then leaves at least RETURN_BUFFER_MIN
# after the last visit ends (RETURN_DEPART is the provisional departure the solver plans against).
RETURN_FILL_END = time(17, 0)
# Below this, the last day takes one stop over the pace cap (not on relaxed pace).
LAST_DAY_FILL_UNTIL = time(15, 0)
RETURN_BUFFER_MIN = 45
RETURN_DEPART = time(17, 45)
# Journey notes as written before the timetable wording, e.g. "Travel: A → B by rail, 3h20".
OLD_JOURNEY_NOTE = re.compile(r"^(Travel|Return): .+ → .+ by (rail|road|air), ")


@dataclass(frozen=True)
class Limits:
    start: time
    end: time
    max_stops: int
    max_travel_min: int
    rest: bool  # elderly: insert rest breaks and keep the day short


def limits(request: TripRequest) -> Limits:
    c = request.constraints
    elderly = any(t.age >= ELDERLY_AGE for t in c.travellers)
    travel = int(c.max_travel_hours_per_day * 60)
    start, end, stops = {
        Pace.relaxed: (time(10), time(17, 30), 2),
        Pace.balanced: (time(9), time(19), 3),
        Pace.packed: (time(8, 30), time(20), 5),
    }[c.pace]
    if c.pace is Pace.relaxed or elderly:
        # Relaxed pace and elderly travellers cap road time at 3 hours a day.
        travel = min(travel, 180)
    if elderly:
        end = min(end, time(18))
    return Limits(start, end, stops, travel, elderly)


class Travel:
    """Cached road minutes and cost between places."""

    def __init__(self, provider: RoadEdgeProvider | None = None) -> None:
        self.provider = provider or HaversineRoadProvider()
        self._cache: dict[tuple[str, str], tuple[int, int]] = {}

    def edge(self, a: Place, b: Place) -> tuple[int, int]:
        key = (a.id, b.id)
        if key not in self._cache:
            e = self.provider.road_edge(_node(a), _node(b))
            # No road edge (too far) counts as a full day of travel, so the solver avoids it.
            self._cache[key] = (round(e.minutes), round(e.cost_inr)) if e else (24 * 60, 0)
        return self._cache[key]

    def minutes(self, a: Place, b: Place) -> int:
        return self.edge(a, b)[0]


def _node(p: Place) -> Node:
    return Node(p.id, KIND_PLACE, p.name, p.lat, p.lng)


def tour_minutes(tour: list[Place], travel: Travel) -> int:
    return sum(travel.minutes(a, b) for a, b in zip(tour, tour[1:]))


def nearest_neighbour(places: list[Place], travel: Travel) -> list[Place]:
    if not places:
        return []
    left = list(places)
    tour = [left.pop(0)]
    while left:
        nxt = min(left, key=lambda p: (travel.minutes(tour[-1], p), p.id))
        left.remove(nxt)
        tour.append(nxt)
    return tour


def two_opt(tour: list[Place], travel: Travel) -> list[Place]:
    """Reverse segments while that shortens the open path. Never returns a longer tour."""
    best, best_len = list(tour), tour_minutes(tour, travel)
    improved = True
    while improved:
        improved = False
        for i in range(1, len(best) - 1):
            for j in range(i + 1, len(best)):
                cand = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                cand_len = tour_minutes(cand, travel)
                if cand_len < best_len:
                    best, best_len, improved = cand, cand_len, True
    return best


def order(places: list[Place], travel: Travel) -> list[Place]:
    return two_opt(nearest_neighbour(places, travel), travel)


def hours_on(place: Place, day: date) -> tuple[time, time] | None:
    """Opening window on that weekday; no listed hours means open all day; None means closed."""
    if not place.opening_hours:
        return time(0), time(23, 59)
    wd = WEEKDAYS[day.weekday()]
    for h in place.opening_hours:
        if h.day == wd:
            return h.opens, h.closes
    return None


@dataclass(frozen=True)
class Visit:
    place: Place
    arrive: datetime
    start: datetime
    leave: datetime


def schedule(day: date, stops: list[Place], travel_min: list[int], lim: Limits) -> tuple[list[Visit], str | None]:
    """Walk the stops in order. Returns the visits and the first problem (None when the day fits).

    travel_min[i] is the travel before stops[i + 1].
    """
    t = datetime.combine(day, lim.start)
    out_since = t
    end = datetime.combine(day, lim.end)
    visits: list[Visit] = []
    for i, p in enumerate(stops):
        if i:
            t += timedelta(minutes=travel_min[i - 1])
            if lim.rest and t - out_since >= timedelta(minutes=REST_AFTER_MIN):
                t += timedelta(minutes=REST_MIN)
                out_since = t
        window = hours_on(p, day)
        if window is None:
            return visits, f"{p.name} is closed on {WEEKDAYS[day.weekday()]}"
        opens, closes = (datetime.combine(day, w) for w in window)
        start = max(t, opens)
        leave = start + timedelta(minutes=p.typical_visit_minutes)
        if leave > closes:
            return visits, f"{p.name} closes at {window[1]:%H:%M}"
        if leave > end:
            return visits, f"{p.name} runs past {lim.end:%H:%M}"
        visits.append(Visit(p, t, start, leave))
        t = leave
    return visits, None


def hop_of(day: DayPlan) -> Leg | None:
    """The journey that opens a day (the outbound trip on day 1, or a move to the next city), if any."""
    if not day.legs:
        return None
    leg = day.legs[0]
    if leg.role in ("outbound", "between"):
        return leg
    # Plans saved before Leg.role: the journey note and a leg that does not start at a stop.
    legacy = leg.role is None and any(n.startswith(HOP_NOTE) for n in day.notes)
    return leg if legacy and leg.from_ not in {p.name for p in day.stops} else None


def out_of(day: DayPlan) -> Leg | None:
    """The journey home that closes the last day, if any."""
    if not day.legs:
        return None
    leg = day.legs[-1]
    if leg.role == "home":
        return leg
    legacy = leg.role is None and any(n.startswith(RETURN_NOTE) for n in day.notes)
    return leg if legacy and leg.to not in {p.name for p in day.stops} else None


MODE_WORD = {Mode.rail: "Train", Mode.road: "Drive", Mode.air: "Flight"}


def _times(leg: Leg) -> str:
    next_day = " (+1 day)" if leg.arrive.date() > leg.depart.date() else ""
    return f"{leg.depart:%H:%M}–{leg.arrive:%H:%M}{next_day}, {_duration(leg)}"


def hop_note(hop: Leg) -> str:
    """e.g. "Train Bengaluru → Mysuru, 06:40–10:00, 3h20"."""
    return f"{MODE_WORD[hop.mode]} {hop.from_} → {hop.to}, {_times(hop)}"


def home_note(out: Leg) -> str:
    """e.g. "Train home Mysuru → Bengaluru, 20:10–23:35, 3h25"."""
    return f"{MODE_WORD[out.mode]} home {out.from_} → {out.to}, {_times(out)}"


def day_titles(days: list[DayPlan], request: TripRequest) -> list[DayPlan]:
    """Give each day a short heading: day number, date and what happens ("Arrive in Mysuru", "Mysuru, then
    home", "Free day in Coorg")."""
    out = []
    for n, d in enumerate(days, 1):
        city = city_of(request, d.date) or request.destinations[0]
        hop, home = hop_of(d), out_of(d)
        if hop and home:
            what = f"{city} day trip"
        elif hop:
            what = f"Arrive in {city}"
        elif home:
            what = f"{city}, then home"
        elif not d.stops:
            what = f"Free day in {city}"
        else:
            what = city
        out.append(d.model_copy(update={"title": f"Day {n} · {d.date:%a %d %b} · {what}"}))
    return out


def local_legs(day: DayPlan) -> list[Leg]:
    """Stop-to-stop legs only: without the journeys that open or close the day."""
    hop, out = hop_of(day), out_of(day)
    return [leg for leg in day.legs if leg is not hop and leg is not out]


def after_hop(lim: Limits, hop: Leg | None) -> Limits:
    """A travel day starts once the journey has arrived, plus time to settle."""
    if hop is None:
        return lim
    ready = hop.arrive + timedelta(minutes=HOP_SETTLE_MIN)
    # An arrival after the day's end (or after midnight) leaves no time for visits that day.
    late = ready.date() != hop.depart.date() or ready.time() >= lim.end
    return replace(lim, start=lim.end if late else max(lim.start, ready.time()))


def before_out(lim: Limits, out: Leg | None) -> Limits:
    """The last day ends early enough to make the journey home."""
    if out is None:
        return lim
    leave_by = (out.depart - timedelta(minutes=RETURN_BUFFER_MIN)).time()
    return replace(lim, end=max(min(lim.end, leave_by), lim.start))


def frame(lim: Limits, hop: Leg | None, out: Leg | None) -> Limits:
    return before_out(after_hop(lim, hop), out)


def build_day(day: date, stops: list[Place], travel: Travel, lim: Limits, reorder: bool = True,
              hop: Leg | None = None, out: Leg | None = None) -> tuple[DayPlan, str | None]:
    """Order (optionally), schedule and attach road legs, between the journey that opens the day (hop)
    and the one that closes it (out), if any. Returns the plan and the first problem."""
    lim = frame(lim, hop, out)
    stops = order(stops, travel) if reorder else list(stops)
    transfer = _transfer(hop, stops[0], travel) if hop and stops and lim.start < lim.end else None
    if transfer and transfer.arrive.date() == day:
        lim = replace(lim, start=max(lim.start, transfer.arrive.time()))
    mins = [travel.minutes(a, b) for a, b in zip(stops, stops[1:])]
    visits, problem = schedule(day, stops, mins, lim)
    rested = any(b.arrive - a.leave > timedelta(minutes=m) for a, b, m in zip(visits, visits[1:], mins))
    legs = []
    for a, b in zip(visits, visits[1:]):
        minutes, cost = travel.edge(a.place, b.place)
        legs.append(Leg(**{"from": a.place.name}, to=b.place.name, mode=Mode.road, depart=a.leave,
                        arrive=a.leave + timedelta(minutes=minutes), minutes=minutes, cost_inr=cost))
    notes = [REST_NOTE] if rested else []
    if transfer:
        legs.insert(0, transfer)
    if hop:
        legs.insert(0, hop)
        notes.insert(0, hop_note(hop))
    if out:
        legs.append(out)
        notes.append(home_note(out))
    times = [StopTime(place_id=v.place.id, arrive=v.arrive, start=v.start, leave=v.leave) for v in visits]
    return DayPlan(date=day, stops=stops, legs=legs, notes=notes, schedule=times), problem


@lru_cache(maxsize=64)
def _city_point(name: str) -> Place | None:
    """Where a journey into a city ends (TY3's city point), as a Place the road provider can route from."""
    from routes.compare import UnknownPlace, resolve_city

    try:
        node = resolve_city(name)
    except UnknownPlace:
        return None
    return Place(id=f"city:{node.id}", name=name, lat=node.lat, lng=node.lon, category="city",
                 typical_visit_minutes=0, source="routes")


def _transfer(hop: Leg, first: Place, travel: Travel) -> Leg | None:
    """The ride from where the journey arrives to the day's first stop, after a short wait (QA #118)."""
    point = _city_point(hop.to)
    if point is None:
        return None
    minutes, cost = travel.edge(point, first)
    depart = hop.arrive + timedelta(minutes=TRANSFER_WAIT_MIN)
    return Leg(**{"from": hop.to}, to=first.name, mode=Mode.road, depart=depart,
               arrive=depart + timedelta(minutes=minutes), minutes=minutes, cost_inr=cost, role="transfer")


def stop_legs(day: DayPlan) -> list[Leg]:
    """Stop-to-stop legs only (no journeys, no transfer)."""
    return [leg for leg in day.legs if leg.role is None]


_KEEP = object()


def rebuild_day(it: Itinerary, d: date, stops: list[Place], travel: Travel, lim: Limits, hop=_KEEP,
                out=_KEEP) -> None:
    """Re-plan one day of an itinerary in place with new stops, keeping its journeys (or a new opening
    journey when `hop` is given) and its own notes; the rest and journey notes are rebuilt with the day."""
    i = next(i for i, x in enumerate(it.days) if x.date == d)
    old = it.days[i]
    plan, _ = build_day(d, stops, travel, lim, hop=hop_of(old) if hop is _KEEP else hop,
                        out=out_of(old) if out is _KEEP else out)
    # Drop only the notes this module wrote for the old day; anything else on the day stays.
    generated = {REST_NOTE} | {hop_note(h) for h in [hop_of(old)] if h} | {home_note(o) for o in [out_of(old)] if o}
    # Plans saved before Leg.role wrote their journey notes as "Travel: ..." and "Return: ...".
    # Journey lines in the older wording ("Travel: A → B by rail, 3h20") are ours too; a traveller's own
    # note that merely starts with "Travel: " is not.
    keep = [n for n in old.notes if n not in generated and not OLD_JOURNEY_NOTE.match(n)]
    it.days[i] = plan.model_copy(update={"notes": keep + plan.notes, "title": old.title})


def journey(a: str, b: str, option: TransportOption, role: str = "between") -> Leg:
    """One leg for a whole transport option, labelled with the two cities (its own legs may be stations)."""
    depart = option.legs[0].depart
    ref = next((leg.ref for leg in option.legs if leg.mode is option.mode and leg.ref), None)
    return Leg(**{"from": a}, to=b, mode=option.mode, depart=depart,
               arrive=depart + timedelta(minutes=option.total_minutes), minutes=option.total_minutes,
               cost_inr=option.total_cost_inr, role=role, ref=ref)


def _duration(leg: Leg) -> str:
    return f"{leg.minutes // 60}h{leg.minutes % 60:02d}"


def fits(day: date, stops: list[Place], travel: Travel, lim: Limits, hop: Leg | None = None,
         out: Leg | None = None) -> bool:
    """The stops fit the day. Only local road time counts against the daily cap; the journeys that open
    or close a day move its start and end instead."""
    if len(stops) > lim.max_stops:
        return False
    plan, problem = build_day(day, stops, travel, lim, hop=hop, out=out)
    return problem is None and sum(leg.minutes for leg in local_legs(plan)) <= lim.max_travel_min


def trip_days(request: TripRequest) -> list[date]:
    return [request.start_date + timedelta(days=i) for i in range((request.end_date - request.start_date).days + 1)]


def split_days(request: TripRequest) -> list[tuple[str, list[date]]]:
    """Share the trip's days between the destinations, in order: request.days_per_destination when set
    (revise moves days with it), else as evenly as possible (earlier cities get the spare days). With
    fewer days than cities, the last cities get none."""
    days = trip_days(request)
    cities = request.destinations
    counts = request.days_per_destination
    if not counts:
        base, extra = divmod(len(days), len(cities))
        counts = [base + (1 if n < extra else 0) for n in range(len(cities))]
    out, i = [], 0
    for city, take in zip(cities, counts):
        out.append((city, days[i:i + take]))
        i += take
    return out


def city_of(request: TripRequest, day: date) -> str | None:
    """Which destination a trip day belongs to (the same split the solver used)."""
    return next((city for city, dates in split_days(request) if day in dates), None)


def solve_trip(request: TripRequest, pools: dict[str, list[Place]], hops: dict[str, Leg] | None = None,
               travel: Travel | None = None, home: Leg | None = None) -> tuple[list[DayPlan], list[Place]]:
    """One solve per destination over its share of the days. The journey into a city (from the origin for
    the first one) opens its first day; the journey home closes the trip's last day."""
    travel = travel or Travel()
    days: list[DayPlan] = []
    left: list[Place] = []
    split = [(c, d) for c, d in split_days(request) if d]
    for city, _ in split_days(request):
        if city not in dict(split):
            left += pools.get(city, [])
    for n, (city, dates) in enumerate(split):
        part = request.model_copy(update={"destinations": [city], "start_date": dates[0], "end_date": dates[-1],
                                          "days_per_destination": None})
        got, rest = solve(part, pools.get(city, []), travel, first_hop=(hops or {}).get(city),
                          last_out=home if n == len(split) - 1 else None)
        days += got
        left += rest
    return days, left


def solve(request: TripRequest, places: list[Place], travel: Travel | None = None,
          first_hop: Leg | None = None, last_out: Leg | None = None) -> tuple[list[DayPlan], list[Place]]:
    """Greedy clustering by distance: each day seeds with the first unplaced place that fits, then adds
    the nearest places that still fit. A day takes its share of what is left (never more than the pace
    allows), so a short list spreads over the trip instead of piling onto day one.
    Returns the day plans and the places that did not fit."""
    travel = travel or Travel()
    lim = limits(request)
    left = list({p.id: p for p in places}.values())  # planner order, one entry per id
    rank = {p.id: i for i, p in enumerate(left)}
    dates = trip_days(request)
    days: list[DayPlan] = []
    for n, d in enumerate(dates):
        hop = first_hop if n == 0 else None
        out = last_out if n == len(dates) - 1 else None
        share = min(lim.max_stops, math.ceil(len(left) / (len(dates) - n)))
        seed = next((p for p in left if fits(d, [p], travel, lim, hop, out)), None)
        chosen = [seed] if seed and share else []
        while chosen and len(chosen) < share:
            # Near the day's stops, but a much more popular place is worth a short detour.
            near = sorted(left, key=lambda p: (min(travel.minutes(c, p) for c in chosen) + RANK_MINUTES * rank[p.id], p.id))
            added = next((p for p in near if p not in chosen and fits(d, [*chosen, p], travel, lim, hop, out)), None)
            if added is None:
                break
            chosen.append(added)
        if out and chosen and len(chosen) == lim.max_stops and request.constraints.pace != Pace.relaxed:
            # The last day (HQ V3-AL): when the pace's cap would end the visits early, one more stop fills it.
            plan, _ = build_day(d, chosen, travel, lim, hop=hop, out=out)
            if plan.schedule and plan.schedule[-1].leave.time() < LAST_DAY_FILL_UNTIL:
                more = replace(lim, max_stops=lim.max_stops + 1)
                near = sorted((p for p in left if p not in chosen),
                              key=lambda p: (min(travel.minutes(c, p) for c in chosen) + RANK_MINUTES * rank[p.id], p.id))
                extra = next((p for p in near if fits(d, [*chosen, p], travel, more, hop, out)), None)
                if extra:
                    chosen.append(extra)
                    days.append(build_day(d, chosen, travel, more, hop=hop, out=out)[0])
                    left = [p for p in left if p not in chosen]
                    continue
        left = [p for p in left if p not in chosen]
        days.append(build_day(d, chosen, travel, lim, hop=hop, out=out)[0])
    return days, left
