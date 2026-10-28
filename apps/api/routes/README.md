# apps/api/routes (TY3 routes)

Multimodal transport graph, Dijkstra and A*, Routes API, SerpApi flights and hotels, seller registry, IRCTC card.

## Files

- `fares.py`: the one fare model. Rail per person by class (a distance-tapering sleeper curve times class multipliers; the class follows the budget style within the classes the train carries), driving per car (fuel Rs 7/km plus tolls on known expressways), cabs per cab (Rs 60 + Rs 18/km, at least Rs 100). Compare, the planner's stop legs (through the road provider) and the IRCTC card all use it.
- `data/cities.json`: the city points and aliases (about 70 cities across India) for compare, stays and the rail build.
- `graph.py`: stations, airports and city points joined by rail, road, air and walk edges; offline fakes for road and air.
- `search.py`: Dijkstra and A* with a time, cost and transfer objective (road and air).
- `timetable.py`: rail on real timetables (datameet corridor subset, `data/README.md`): earliest arrival by connection scan with changes, then the latest departure that arrives as early.
- `roads.py`: road edges from the Google Routes API (`GOOGLE_MAPS_API_KEY`), cached in the shared store, capped at 100 live calls per process and `ROUTES_MONTHLY_CAP` (default 2000) for all instances, haversine fallback.
- `apicache.py`: the shared response cache and live-call counters (Postgres tables `routes_api_cache` and `routes_api_calls` when `DATABASE_URL` is set, else the JSON file `ROUTES_CACHE_FILE`, default in the temp dir).
- `serpapi.py`: SerpApi client (`SERPAPI_API_KEY`): cache first, then one live call if `SERPAPI_DAILY_CAP` (default 20) and `SERPAPI_MONTHLY_CAP` (default 100) allow, then the stale cached answer, then None. Responses are sanitised before caching; a failed call is not retried for 10 minutes.
- `flights.py`: Google Flights (one way, economy, one adult; cached 6 hours) and booking options (prices by seller).
- `hotels.py`: Google Hotels (two adults a room; cached 12 hours) and property details (prices by source, top stay only).
- `sellers.py`: seller registry. Deep links for Booking.com, Airbnb, MakeMyTrip; "Check price" links for Goibibo, Cleartrip, ixigo; SerpApi quotes merged in; unknown sellers get a Google search link.
- `compare.py`: `POST /routes/compare`.
- `irctc.py`: `GET /routes/irctc-card` and `GET /routes/pnr-mock` (sample data only; there is no IRCTC API and we never scrape it).
- `metrics.py`: `POST /routes/metrics/event`, `GET /routes/metrics/summary` (user-study timing).
- `stays.py`: `rank_stays(..., limit=5, budget_style=None)` for TY1's planner: Google Hotels when `SERPAPI_API_KEY` is set (no answer: no stays, never samples), else fictional sample stays marked `sample=True`. Stays carry `id`, `stars`, `rating`, `reviews`, `kind` and `offers`; rentals too big for the party are dropped (one spare bedroom at most); ordered by `budget_style` (budget: cheapest good one; mid: 3-4 star by rating; luxury: most stars), stays with no rating or under 10 reviews last.
- `scripts/record_live.py`: the live smoke and fixture recorder (never run by tests; `--no-road` makes no Routes API call).

## POST /routes/compare

Request:

```json
{"origin": "Bengaluru", "destination": "Goa", "date": "2026-12-11",
 "depart_time": "08:00", "rank_by": "balanced", "modes": ["rail", "road", "air"], "travellers": 4}
```

Only `origin` and `destination` are required. Cities come from `data/cities.json`
(about 70 across India, with aliases such as Bangalore, Cochin, Trivandrum, Alleppey,
New Delhi); an unknown city or the same city twice gives 422.
`rank_by` is `balanced` (time and cost relative to the best, plus a quarter per
change, plus 1.5 for an overnight train when a daytime option exists and the
trip is short, its daytime option at most 8 h, or one person travels alone),
`time`, `cost` or `changes`. An overnight train is one running past midnight or
before 05:00; when every option is overnight, or it is the only one, it keeps
its place.

Response: `origin`, `destination`, `date`, `rank_by`, `options[]` and
`unavailable[]` (a mode with no route and the reason), plus `notes[]`. Each option
is `{id, rank, changes, score, sources, option}`, where `option` is the contract
`TransportOption`. Legs are one per vehicle, with readable names in `from`/`to`.
Walk legs use mode `road` (the contract has no walk mode). Costs are for the
whole party (`fares.py`): rail per person in the class the budget style rides,
air per person, a drive between cities as fuel and tolls per car of four, and
rides to and from stations and airports as cab fares per cab of four. In process,
`compare(req, rail_class="budget" | "mid" | "luxury")` sets the style (default mid).

Air: with `SERPAPI_API_KEY` set, each airport pair within 60 km of the two cities
gets one live flight: of those you can reach (ground transfer plus 60 min at the
airport after `depart_time`), the best on arrival time plus fare (Rs 10 a
minute). The flight leg starts 60 min before take-off, so the option may leave
later than `depart_time`. Estimated connections through other airports are
dropped; a pair with no live answer keeps its estimate (`fake_air`). The air
option's `offers[]` lists every seller (prices for the whole party, cheapest
first). `sources` may include `serpapi_flights`.

Rail: real departure times. The option leaves the city centre in time for the
first train (road or walk to one of the city's stations, plus 15 min at the
station), waits between trains (15 min minimum change), and goes on by road
from the last station; `total_minutes` is door to door including waits, so the
first leg can leave later than `depart_time`. `sources` has `datameet_rail`
(or `sample_rail` on the fallback).

In process, for choosing a departure (TY1):
`routes.compare.get_service().rail_departures(origin, destination, day,
earliest=time(5, 0), latest=time(23, 59), travellers=1, limit=6)` gives the
rail journeys leaving in that window, in order, each a `TransportOption`;
`legs[0].depart` is when to leave, `legs[-1].arrive` when you are there.

In process (no HTTP): `routes.compare.get_service().compare(CompareRequest(...))`.

## GET /routes/irctc-card

`?from=SBC&to=MAO&date=2026-12-11&party=goa_family[&train=17309][&after=07:00][&travel_class=3A][&style=mid]`.
With no `train`, the first train leaving at or after `after` (default 06:00). `classes` lists the
classes the train carries (Shatabdis: CC, EC); with no `travel_class`, or one the train lacks (a note
says so), the card uses the class compare prices the train in for `style`, so its fare is the plan's.
`from`/`to` take a station code or the station name from a compare rail leg. `party`
is a sample persona (`goa_family`, `mysuru_weekend`), or `none` for a real trip: "Passenger 1..N"
rows with the ages in `ages=34,64,58,9` (or `travellers` rows), gender left blank, `sample: false`.
No names go in the URL.
Returns the train, stations, departure and arrival, passengers with berth
preferences (Lower from age 45), a whole-party fare estimate, `copy_text` in
IRCTC's form order and `booking_url`. 404 when no sample train runs from→to.

## GET /routes/pnr-mock

`?pnr=1234567890[&at=2026-12-11T20:00:00+05:30]`. Replays `data/sample_pnrs.json`
up to `at` (default now): `timeline`, `current_status`, per-passenger status,
`chart_prepared`. Unknown PNR: 404 `"unknown sample PNR"`.

## GET /routes/usage

Live calls counted in the shared store: `serpapi` (this month and today, with
`SERPAPI_MONTHLY_CAP` and `SERPAPI_DAILY_CAP`) and `routes_api` (this month, with
`ROUTES_MONTHLY_CAP`). Counts only. At a cap, calls stop and cached answers are used. `serpapi.plan_left`
is the plan's remainder at the last account check (null before one). Before each live SerpApi call
the client reads the plan's searches left from SerpApi's Account API (free, not counted; cached 10
minutes) and stops `SERPAPI_RESERVE` (default 10) short of it, whatever the caps say.

## Metrics

`POST /routes/metrics/event` with `{session_id, task, arm: ty|baseline, event:
start|plan_shown|booking_chosen, at?}`. The body is parsed as JSON whatever the
Content-Type, so `navigator.sendBeacon` (text/plain) works. `session_id` is a
random id (8-64 of `[A-Za-z0-9_-]`); phone-like ids and extra fields are
rejected. Stored in Postgres (`routes_metric_events`, created if missing) when
`DATABASE_URL` is set (at most 200,000 rows, then 503 and nothing is
overwritten), else in memory. At most 60 events a minute per client IP (the
last `X-Forwarded-For` entry), per instance; more get 429. No token: anything
in the browser bundle is public. `GET /routes/metrics/summary` gives,
per task and arm, sessions and the median seconds from a session's first
`start` to its first `plan_shown` and `booking_chosen`.

## Known limits

- Rail is datameet's timetable from about 2016, every train treated as daily, for the stations in the Karnataka-Goa box and within 40 km of each city (long-distance trains only outside the box); fares are fitted estimates (`fares.py`), not IRCTC's fare table. `ROUTES_RAIL=sample` switches to the fictional sample network.
- Air is the fake network unless `SERPAPI_API_KEY` is set. Live flight booking links need a POST, so seller offers for flights link to each seller's search, not the exact fare.
- Hotel rates assume two adults a room; the party price is rooms x the room rate. Only the top stay gets per-source prices (one details call); the others show registry links.
- Road uses the haversine fake unless `GOOGLE_MAPS_API_KEY` is set. Cache and monthly cap are shared through the store; the 100-call cap is per process.
- The metrics rate limit is per instance, in memory.
- Tolls are known only for a few expressways (`fares.TOLLS_INR`); other drives show fuel only.
