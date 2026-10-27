# data (TY2 guide)

Sample and seed data only. No real phone numbers or personal data.

## Google Places ids (corridors)

`guide/scripts/enrich_places.py` matches corridor POIs to Google Places API (New),
one Enterprise Text Search per place, every call logged in `corridor/places_calls.log`.
Places terms let us store the `place_id` only, so that and `places_status` (`hours`,
`no-hours`, `no-match`, `not-found`) are all the repo keeps. Opening hours are fetched
at runtime by `guide.hours.live_hours` for places with status `hours`, cached privately
in Cloud SQL. In the repo, corridor hours stay `hours-unverified` and fees
`fee-unverified` (Places has no admission fees).
