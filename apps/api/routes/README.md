# apps/api/routes (TY3 routes)

Multimodal transport graph, Dijkstra and A*, Routes API, SerpApi flights and hotels, seller registry, IRCTC card.

## Files

- `graph.py`: stations, airports and city points joined by rail, road, air and walk edges; offline fakes for road and air.
- `search.py`: Dijkstra and A* with a time, cost and transfer objective.
- `roads.py`: road edges from the Google Routes API (`GOOGLE_MAPS_API_KEY`), cached, capped at 100 live calls per process, haversine fallback.
- `compare.py`: `POST /routes/compare`.

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

## Known limits

- Rail is the sample timetable subset (fictional trains); waits for departures are not modelled, so legs run back to back from `depart_time`.
- Air is the fake network until SerpApi flights (P2); `offers` is empty until the seller registry lands.
- Road uses the haversine fake unless `GOOGLE_MAPS_API_KEY` is set.
