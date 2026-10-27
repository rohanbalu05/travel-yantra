# apps/api/routes (TY3 routes)

Multimodal transport graph, Dijkstra and A*, Routes API, SerpApi flights and hotels, seller registry, IRCTC card.

## Files

- `graph.py`: stations, airports and city points joined by rail, road, air and walk edges; offline fakes for road and air.
- `search.py`: Dijkstra and A* with a time, cost and transfer objective.
- `roads.py`: road edges from the Google Routes API (`GOOGLE_MAPS_API_KEY`), cached, capped at 100 live calls per process, haversine fallback.
- `compare.py`: `POST /routes/compare`.
- `irctc.py`: `GET /routes/irctc-card` and `GET /routes/pnr-mock` (sample data only; there is no IRCTC API and we never scrape it).
- `metrics.py`: `POST /routes/metrics/event`, `GET /routes/metrics/summary` (user-study timing).
- `stays.py`: `rank_stays(...)` for TY1's planner (sample stays until SerpApi Hotels).

## POST /routes/compare

Request:

```json
{"origin": "Bengaluru", "destination": "Goa", "date": "2026-12-11",
 "depart_time": "08:00", "rank_by": "balanced", "modes": ["rail", "road", "air"], "travellers": 4}
```

Only `origin` and `destination` are required. Cities come from a sample table in
`compare.py` (`CITIES`, `ALIASES`); an unknown city or the same city twice gives 422.
`rank_by` is `balanced` (time and cost relative to the best, plus a quarter per
change), `time`, `cost` or `changes`.

Response: `origin`, `destination`, `date`, `rank_by`, `options[]` and
`unavailable[]` (a mode with no route and the reason), plus `notes[]`. Each option
is `{id, rank, changes, score, sources, option}`, where `option` is the contract
`TransportOption`. Legs are one per vehicle, with readable names in `from`/`to`.
Walk legs use mode `road` (the contract has no walk mode). Costs are for the
whole party: rail and air per person, road per car of four.

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
`DATABASE_URL` is set, else in memory. `GET /routes/metrics/summary` gives,
per task and arm, sessions and the median seconds from a session's first
`start` to its first `plan_shown` and `booking_chosen`.

## Known limits

- Rail is the sample timetable subset (fictional trains); waits for departures are not modelled, so legs run back to back from `depart_time`.
- Air is the fake network until SerpApi flights (P2); `offers` is empty until the seller registry lands.
- Road uses the haversine fake unless `GOOGLE_MAPS_API_KEY` is set. `default_road_provider()` is one shared instance per process: 100 live calls, then haversine. The cap and the 7-day cache are per instance, not shared.
- IRCTC fares are an estimate (class multipliers on a per-km rate), not IRCTC's fare table.
