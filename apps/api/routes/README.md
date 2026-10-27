# apps/api/routes (TY3 routes)

Multimodal transport graph, Dijkstra and A*, Routes API, SerpApi flights and hotels, seller registry, IRCTC card.

## Files

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
- `stays.py`: `rank_stays(...)` for TY1's planner: Google Hotels when `SERPAPI_API_KEY` is set, else fictional sample stays; every stay has `offers`.
- `scripts/record_live.py`: the live smoke and fixture recorder (never run by tests; `--no-road` makes no Routes API call).

## POST /routes/compare

Request:

```json
{"origin": "Bengaluru", "destination": "Goa", "date": "2026-12-11",
 "depart_time": "08:00", "rank_by": "balanced", "modes": ["rail", "road", "air"], "travellers": 4}
```

Only `origin` and `destination` are required. Cities come from a sample table in
`compare.py` (`CITIES`, `ALIASES`; includes Coorg/Madikeri, Hampi and
Chikmagalur); an unknown city or the same city twice gives 422.
`rank_by` is `balanced` (time and cost relative to the best, plus a quarter per
change), `time`, `cost` or `changes`.

Response: `origin`, `destination`, `date`, `rank_by`, `options[]` and
`unavailable[]` (a mode with no route and the reason), plus `notes[]`. Each option
is `{id, rank, changes, score, sources, option}`, where `option` is the contract
`TransportOption`. Legs are one per vehicle, with readable names in `from`/`to`.
Walk legs use mode `road` (the contract has no walk mode). Costs are for the
whole party: rail and air per person, road per car of four.

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

`?from=SBC&to=MAO&date=2026-12-11&travel_class=3A&party=goa_family[&train=90001]`.
`from`/`to` take a station code or the station name from a compare rail leg. `party`
is a sample persona (`goa_family`, `mysuru_weekend`); no names go in the URL.
Returns the train, stations, departure and arrival, passengers with berth
preferences (Lower from age 45), a whole-party fare estimate, `copy_text` in
IRCTC's form order and `booking_url`. 404 when no sample train runs from→to.

## GET /routes/pnr-mock

`?pnr=1234567890[&at=2026-12-11T20:00:00+05:30]`. Replays `data/sample_pnrs.json`
up to `at` (default now): `timeline`, `current_status`, per-passenger status,
`chart_prepared`. Unknown PNR: 404 `"unknown sample PNR"`.

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

- Rail is datameet's timetable from about 2016, every train treated as daily; fares are per-km estimates. `ROUTES_RAIL=sample` switches to the fictional sample network.
- Air is the fake network unless `SERPAPI_API_KEY` is set. Live flight booking links need a POST, so seller offers for flights link to each seller's search, not the exact fare.
- Hotel rates assume two adults a room; the party price is rooms x the room rate. Only the top stay gets per-source prices (one details call); the others show registry links.
- Road uses the haversine fake unless `GOOGLE_MAPS_API_KEY` is set. Cache and monthly cap are shared through the store; the 100-call cap is per process.
- The metrics rate limit is per instance, in memory.
- IRCTC fares are an estimate (class multipliers on a per-km rate), not IRCTC's fare table.
