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
# Lunch: the first time the day reaches LUNCH_FROM..LUNCH_UNTIL without a food stop, LUNCH_MIN off.
LUNCH_FROM = time(12, 30)
LUNCH_UNTIL = time(14, 0)
LUNCH_MIN = 45
LUNCH_NOTE = re.compile(r"^Lunch \d\d:\d\d–\d\d:\d\d$")
FOOD = "food"
# Stops whose opening hours nobody knows (TY2: no Places match, or Places has none): said, never guessed.
CHECK_HOURS = "Check hours before you go: "
# A travel-only day's first note (and title): "Travel day: train 17309, 15:15 → 05:47".
TRAVEL_DAY = "Travel day: "
# Grouping by area: a day's stops stay within this road time of one another, and the first and last days
# (arrival and departure) start from places near where the journey arrives or leaves.
CLUSTER_MIN = 60
# One site, one day: places this close are one site (Chamundeshwari Temple, the Nandi statue and the 1000 steps
# on Chamundi Hill), by distance, chained; Mysore Palace and Devaraja Market (0.8 km) stay two.
SITE_KM = 0.75
# A departure day: the last visit ends with time to ride to the station or airport (the city point routes
# uses), plus this, before the journey home leaves.
DEPART_BUFFER_MIN = 15
# The last day takes one stop over the pace cap only when the journey home leaves this long after the visits.
FILL_GAP_MIN = 150
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
    # Lunch taken on arriving, before the visit starts.
    lunch: datetime | None = None


def lunch_at(t: datetime, lunched: bool) -> datetime | None:
    """When lunch starts if the day reaches the lunch window at t and has not eaten yet."""
    if lunched:
        return None
    day = t.date()
    return t if datetime.combine(day, LUNCH_FROM) <= t <= datetime.combine(day, LUNCH_UNTIL) else None


def km(a: Place, b: Place) -> float:
    dlat, dlng = math.radians(b.lat - a.lat), math.radians(b.lng - a.lng)
    h = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a.lat)) * math.cos(math.radians(b.lat)) * math.sin(dlng / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def sites(places: list[Place]) -> dict[str, str]:
    """Place id -> site id: places within SITE_KM of one another, chained, are one site."""
    parent = {p.id: p.id for p in places}

    def root(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(places):
        for b in places[i + 1:]:
            if km(a, b) < SITE_KM:
                parent[root(a.id)] = root(b.id)
    return {p.id: root(p.id) for p in places}


def to_station(stops: list[Place], out: Leg | None, travel: Travel) -> int:
    """Minutes from the day's last stop to where the journey home starts (the city point), 0 when unknown."""
    if not out or not stops or (point := _city_point(out.from_)) is None:
        return 0
    return travel.minutes(stops[-1], point)


def in_area(stops: list[Place], place: Place, travel: Travel) -> bool:
    """A day takes a moved stop only in its own area (or when it has no stops yet)."""
    return not stops or min(travel.minutes(s, place) for s in stops) <= CLUSTER_MIN


def ate(p: Place, start: datetime, leave: datetime) -> bool:
    """A food stop over the lunch window is lunch."""
    return p.category == FOOD and start.time() <= LUNCH_UNTIL and leave.time() >= LUNCH_FROM


def schedule(day: date, stops: list[Place], travel_min: list[int], lim: Limits) -> tuple[list[Visit], str | None]:
    """Walk the stops in order. Returns the visits and the first problem (None when the day fits).

    travel_min[i] is the travel before stops[i + 1].
    """
    t = datetime.combine(day, lim.start)
    out_since = t
    end = datetime.combine(day, lim.end)
    visits: list[Visit] = []
    lunched = False  # a food stop over the window counts (ate)
    for i, p in enumerate(stops):
        if i:
            t += timedelta(minutes=travel_min[i - 1])
            if lim.rest and t - out_since >= timedelta(minutes=REST_AFTER_MIN):
                t += timedelta(minutes=REST_MIN)
                out_since = t
        arrive = t
        lunch = None if p.category == FOOD else lunch_at(t, lunched)
        if lunch:
            t, lunched, out_since = t + timedelta(minutes=LUNCH_MIN), True, t + timedelta(minutes=LUNCH_MIN)
        window = hours_on(p, day)
        if window is None:
            return visits, f"{p.name} is closed on {WEEKDAYS[day.weekday()]}"
        opens, closes = (datetime.combine(day, w) for w in window)
        start = max(t, opens)
        leave = start + timedelta(minutes=p.typical_visit_minutes)
        noon = datetime.combine(day, LUNCH_FROM)
        if not lunched and not lunch and p.category != FOOD and start < noon < leave:
            # A long visit over midday (a waterfall, a fort): lunch there, and the visit takes that much longer.
            lunch, leave, lunched = noon, leave + timedelta(minutes=LUNCH_MIN), True
        if leave > closes:
            return visits, f"{p.name} closes at {window[1]:%H:%M}"
        if leave > end:
            return visits, f"{p.name} runs past {lim.end:%H:%M}"
        lunched = lunched or ate(p, start, leave)
        visits.append(Visit(p, arrive, start, leave, lunch))
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


def no_time(day: date, lim: Limits, hop: Leg | None, out: Leg | None) -> bool:
    """The journeys leave less than two hours for visits that day (or none at all)."""
    f = frame(lim, hop, out, day)
    return datetime.combine(day, f.end) - datetime.combine(day, f.start) < timedelta(hours=2)


def travel_day(legs: list[Leg]) -> str:
    """"Travel day: train 17309, 15:15 → 05:47" for the journeys of a day with no visits."""
    parts = []
    for leg in legs:
        what = MODE_WORD[leg.mode].lower() + (f" {leg.ref}" if leg.ref else "")
        parts.append(f"{what}, {leg.depart:%H:%M} → {leg.arrive:%H:%M}")
    return TRAVEL_DAY + "; ".join(parts)


def day_titles(days: list[DayPlan], request: TripRequest) -> list[DayPlan]:
    """Give each day a short heading: day number, date and what happens ("Arrive in Mysuru", "Mysuru, then
    home", "Free day in Coorg")."""
    out = []
    for n, d in enumerate(days, 1):
        city = city_of(request, d.date) or request.destinations[0]
        hop, home = hop_of(d), out_of(d)
        if not d.stops and (hop or home) and no_time(d.date, limits(request), hop, home):
            what = travel_day([leg for leg in (hop, home) if leg])
        elif hop and home:
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


def after_hop(lim: Limits, hop: Leg | None, day: date | None = None) -> Limits:
    """A travel day starts once the journey has arrived, plus time to settle."""
    if hop is None:
        return lim
    ready = hop.arrive + timedelta(minutes=HOP_SETTLE_MIN)
    # An arrival after the day's end (or the next day) leaves no time for visits that day. The day is the
    # trip day the journey opens: a night train booked the evening before arrives on it, in time.
    late = ready.date() > (day or hop.depart.date()) or ready.time() >= lim.end
    return replace(lim, start=lim.end if late else max(lim.start, ready.time()))


def before_out(lim: Limits, out: Leg | None) -> Limits:
    """The last day ends early enough to make the journey home."""
    if out is None:
        return lim
    leave_by = (out.depart - timedelta(minutes=RETURN_BUFFER_MIN)).time()
    return replace(lim, end=max(min(lim.end, leave_by), lim.start))


def frame(lim: Limits, hop: Leg | None, out: Leg | None, day: date | None = None) -> Limits:
    return before_out(after_hop(lim, hop, day), out)


def build_day(day: date, stops: list[Place], travel: Travel, lim: Limits, reorder: bool = True,
              hop: Leg | None = None, out: Leg | None = None) -> tuple[DayPlan, str | None]:
    """Order (optionally), schedule and attach road legs, between the journey that opens the day (hop)
    and the one that closes it (out), if any. Returns the plan and the first problem."""
    lim = frame(lim, hop, out, day)
    stops = order(stops, travel) if reorder else list(stops)
    if out and stops:
        # Departure day: leave the last stop in time to ride to the station or airport, plus a buffer.
        ride = to_station(stops, out, travel) + DEPART_BUFFER_MIN
        lim = replace(lim, end=max(min(lim.end, (out.depart - timedelta(minutes=ride)).time()), lim.start))
    transfer = _transfer(hop, stops[0], travel) if hop and stops and lim.start < lim.end else None
    if transfer and transfer.arrive.date() == day:
        lim = replace(lim, start=max(lim.start, transfer.arrive.time()))
    mins = [travel.minutes(a, b) for a, b in zip(stops, stops[1:])]
    visits, problem = schedule(day, stops, mins, lim)
    rested = any(b.arrive - a.leave > timedelta(minutes=m) for a, b, m in zip(visits, visits[1:], mins))
    rested = rested and lim.rest
    lunch = next((v.lunch for v in visits if v.lunch), None)
    if not lunch and visits and not any(ate(v.place, v.start, v.leave) for v in visits) and \
            LUNCH_FROM <= visits[-1].leave.time() <= LUNCH_UNTIL:
        lunch = visits[-1].leave  # after the day's last visit
    legs = []
    for a, b in zip(visits, visits[1:]):
        minutes, cost = travel.edge(a.place, b.place)
        legs.append(Leg(**{"from": a.place.name}, to=b.place.name, mode=Mode.road, depart=a.leave,
                        arrive=a.leave + timedelta(minutes=minutes), minutes=minutes, cost_inr=cost))
    notes = [REST_NOTE] if rested else []
    if lunch:
        notes.append(f"Lunch {lunch:%H:%M}–{lunch + timedelta(minutes=LUNCH_MIN):%H:%M}")
    if unknown := [p.name for p in stops if not p.opening_hours]:
        notes.append(CHECK_HOURS + ", ".join(unknown))
    if transfer:
        legs.insert(0, transfer)
    if hop:
        legs.insert(0, hop)
        notes.insert(0, hop_note(hop))
    if out:
        legs.append(out)
        notes.append(home_note(out))
    if not stops and (hop or out) and no_time(day, lim, hop, out):
        notes.insert(0, travel_day([leg for leg in (hop, out) if leg]))
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
    keep = [n for n in old.notes if n not in generated and not OLD_JOURNEY_NOTE.match(n)
            and not LUNCH_NOTE.match(n) and not n.startswith((TRAVEL_DAY, CHECK_HOURS))]
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
    site = sites(left)
    taken: set[str] = set()  # sites already visited on an earlier day
    dates = trip_days(request)
    days: list[DayPlan] = []

    def ok(p: Place, chosen: list[Place]) -> bool:
        """At most one food stop a day; a site's places only on the day that visits it."""
        return not (p.category == FOOD and any(c.category == FOOD for c in chosen)) and site[p.id] not in taken
    # Where journeys arrive and leave: the first and last days start near it, so a far sight (Dudhsagar)
    # goes to a full day in the middle, not to an arrival afternoon.
    centre = _city_point(request.destinations[0])
    for n, d in enumerate(dates):
        hop = first_hop if n == 0 else None
        out = last_out if n == len(dates) - 1 else None
        share = min(lim.max_stops, math.ceil(len(left) / (len(dates) - n)))
        edge = (hop or out) and centre is not None and len(dates) > 1
        seeds = sorted(left, key=lambda p: (RANK_MINUTES * rank[p.id] + (travel.minutes(centre, p) if edge else 0), p.id))
        seed = next((p for p in seeds if ok(p, []) and fits(d, [p], travel, lim, hop, out)), None)
        chosen = [seed] if seed and share else []
        while chosen and len(chosen) < share:
            # Near the day's stops (one area a day), but a much more popular place is worth a short detour.
            near = sorted((p for p in left if p not in chosen and min(travel.minutes(c, p) for c in chosen) <= CLUSTER_MIN),
                          key=lambda p: (min(travel.minutes(c, p) for c in chosen) + RANK_MINUTES * rank[p.id], p.id))
            added = next((p for p in near if ok(p, chosen) and fits(d, [*chosen, p], travel, lim, hop, out)), None)
            if added is None:
                break
            chosen.append(added)
        # One site, one day: the rest of a site the day visits comes along when it fits (one over the cap at
        # most), else it is left out; never on another day.
        for p in [p for p in left if p not in chosen and chosen and site[p.id] in {site[c.id] for c in chosen}]:
            if len(chosen) < lim.max_stops and ok(p, chosen) and \
                    fits(d, [*chosen, p], travel, lim, hop, out):
                chosen.append(p)
        taken.update(site[c.id] for c in chosen)
        if out and chosen and len(chosen) == lim.max_stops and request.constraints.pace != Pace.relaxed:
            # The last day (HQ V3-AL): when the pace's cap would end the visits long before the journey home,
            # one more stop fills it; never crammed in before an early train (D-56).
            plan, _ = build_day(d, chosen, travel, lim, hop=hop, out=out)
            idle = out.depart - plan.schedule[-1].leave if plan.schedule else timedelta(0)
            if plan.schedule and plan.schedule[-1].leave.time() < LAST_DAY_FILL_UNTIL \
                    and idle > timedelta(minutes=FILL_GAP_MIN):
                more = replace(lim, max_stops=lim.max_stops + 1)
                near = sorted((p for p in left if p not in chosen
                               and min(travel.minutes(c, p) for c in chosen) <= CLUSTER_MIN),
                              key=lambda p: (min(travel.minutes(c, p) for c in chosen) + RANK_MINUTES * rank[p.id], p.id))
                extra = next((p for p in near if ok(p, chosen) and fits(d, [*chosen, p], travel, more, hop, out)), None)
                if extra:
                    chosen.append(extra)
                    days.append(build_day(d, chosen, travel, more, hop=hop, out=out)[0])
                    left = [p for p in left if p not in chosen]
                    continue
        left = [p for p in left if p not in chosen]
        days.append(build_day(d, chosen, travel, lim, hop=hop, out=out)[0])
    return days, left
