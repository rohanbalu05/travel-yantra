"""Deterministic day solver: cluster places into days, order each day, schedule within opening hours.

No model calls. Travel times come from TY3's RoadEdgeProvider (HaversineRoadProvider offline).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta

from routes.graph import KIND_PLACE, HaversineRoadProvider, Node, RoadEdgeProvider
from ty_contracts import DayPlan, Leg, Mode, Pace, Place, TripRequest

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
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
    """The inter-city leg that opens a travel day, if any. Stop-to-stop legs always start at a stop."""
    if day.legs and (not day.stops or day.legs[0].from_ not in {p.name for p in day.stops}):
        return day.legs[0]
    return None


def after_hop(lim: Limits, hop: Leg | None) -> Limits:
    """A travel day starts once the hop has arrived (plus time to settle) and has less road time left."""
    if hop is None:
        return lim
    start = max(lim.start, (hop.arrive + timedelta(minutes=HOP_SETTLE_MIN)).time())
    return replace(lim, start=min(start, lim.end), max_travel_min=max(lim.max_travel_min - hop.minutes, 0))


def build_day(day: date, stops: list[Place], travel: Travel, lim: Limits, reorder: bool = True,
              hop: Leg | None = None) -> tuple[DayPlan, str | None]:
    """Order (optionally), schedule and attach road legs (after the inter-city hop, if any).
    Returns the plan and the first problem."""
    lim = after_hop(lim, hop)
    stops = order(stops, travel) if reorder else list(stops)
    mins = [travel.minutes(a, b) for a, b in zip(stops, stops[1:])]
    visits, problem = schedule(day, stops, mins, lim)
    rested = any(b.arrive - a.leave > timedelta(minutes=m) for a, b, m in zip(visits, visits[1:], mins))
    legs = []
    for a, b in zip(visits, visits[1:]):
        minutes, cost = travel.edge(a.place, b.place)
        legs.append(Leg(**{"from": a.place.name}, to=b.place.name, mode=Mode.road, depart=a.leave,
                        arrive=a.leave + timedelta(minutes=minutes), minutes=minutes, cost_inr=cost))
    notes = [REST_NOTE] if rested else []
    if hop:
        legs.insert(0, hop)
        notes.insert(0, f"{HOP_NOTE}{hop.from_} → {hop.to} by {hop.mode.value}, {hop.minutes // 60}h{hop.minutes % 60:02d}")
    return DayPlan(date=day, stops=stops, legs=legs, notes=notes), problem


def fits(day: date, stops: list[Place], travel: Travel, lim: Limits, hop: Leg | None = None) -> bool:
    if len(stops) > lim.max_stops:
        return False
    plan, problem = build_day(day, stops, travel, lim, hop=hop)
    return problem is None and sum(leg.minutes for leg in plan.legs) <= lim.max_travel_min


def trip_days(request: TripRequest) -> list[date]:
    return [request.start_date + timedelta(days=i) for i in range((request.end_date - request.start_date).days + 1)]


def split_days(request: TripRequest) -> list[tuple[str, list[date]]]:
    """Share the trip's days between the destinations, in order, as evenly as possible (earlier cities
    get the spare days). With fewer days than cities, the last cities get none."""
    days = trip_days(request)
    cities = request.destinations
    base, extra = divmod(len(days), len(cities))
    out, i = [], 0
    for n, city in enumerate(cities):
        take = base + (1 if n < extra else 0)
        out.append((city, days[i:i + take]))
        i += take
    return out


def city_of(request: TripRequest, day: date) -> str | None:
    """Which destination a trip day belongs to (the same split the solver used)."""
    return next((city for city, dates in split_days(request) if day in dates), None)


def solve_trip(request: TripRequest, pools: dict[str, list[Place]], hops: dict[str, Leg] | None = None,
               travel: Travel | None = None) -> tuple[list[DayPlan], list[Place]]:
    """One solve per destination over its share of the days; the hop into a city opens its first day."""
    travel = travel or Travel()
    days: list[DayPlan] = []
    left: list[Place] = []
    for city, dates in split_days(request):
        if not dates:
            left += pools.get(city, [])
            continue
        part = request.model_copy(update={"destinations": [city], "start_date": dates[0], "end_date": dates[-1]})
        got, rest = solve(part, pools.get(city, []), travel, first_hop=(hops or {}).get(city))
        days += got
        left += rest
    return days, left


def solve(request: TripRequest, places: list[Place], travel: Travel | None = None,
          first_hop: Leg | None = None) -> tuple[list[DayPlan], list[Place]]:
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
        share = min(lim.max_stops, math.ceil(len(left) / (len(dates) - n)))
        seed = next((p for p in left if fits(d, [p], travel, lim, hop)), None)
        chosen = [seed] if seed and share else []
        while chosen and len(chosen) < share:
            # Near the day's stops, but a much more popular place is worth a short detour.
            near = sorted(left, key=lambda p: (min(travel.minutes(c, p) for c in chosen) + RANK_MINUTES * rank[p.id], p.id))
            added = next((p for p in near if p not in chosen and fits(d, [*chosen, p], travel, lim, hop)), None)
            if added is None:
                break
            chosen.append(added)
        left = [p for p in left if p not in chosen]
        days.append(build_day(d, chosen, travel, lim, hop=hop)[0])
    return days, left
