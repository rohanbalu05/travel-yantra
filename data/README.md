# data (TY2 guide)

Sample and seed data only. No real phone numbers or personal data.

## Opening hours from Google Places (corridors)

`guide/scripts/enrich_places.py` fills `opens`, `closes` and `closed_on` of corridor
POIs from Places API (New), one Enterprise Text Search per place, every call logged in
`corridor/places_calls.log`. Tags say what is confirmed: `hours-places` (with `place_id`,
`hours_checked` and Places' own `hours_text`), `hours-break` (closed at midday),
`hours-vary` (some days differ), `hours-unverified` (no match, or Places has no hours).
Places has no admission fees, so every corridor fee stays `fee-unverified`.
