---
name: travel-yantra
description: Plan trips in India (multi-city, road, rail and air with prices), revise them, compare transport between two cities, tell the story (Katha) of a place, answer travel and emergency questions, in English, Hindi, Kannada, Tamil, Telugu or Bengali. Use for any India trip planning or travel question.
metadata: {"openclaw": {"requires": {"bins": ["python3"]}, "homepage": "https://github.com/rohanbalu05/travel-yantra"}}
---

# Travel Yantra

Travel Yantra is a travel companion for India. Run the helper with the user's words and
reply from the JSON it prints. Every command prints one JSON object; on failure it prints
`{"error": "..."}` and exits 1. Tell the user the error in plain words and do not retry
more than once.

```
python3 {baseDir}/scripts/ty.py <command> ...
```

## Commands

| User wants | Command |
| --- | --- |
| A trip plan | `plan "<their trip in their words>" [--lang hi]` |
| Change a plan | `revise <plan_id> <intent> [--day YYYY-MM-DD] [--place-id ID] [--city NAME] [--mode road\|rail\|air]` |
| Road vs rail vs air | `compare <from> <to> [--on YYYY-MM-DD] [--rank-by balanced\|time\|cost\|changes]` |
| The story of a place | `katha "<place>" [--minutes 2\|5\|10] [--lang hi] [--kind city]` |
| A question (history, food, nearest hospital) | `ask "<question>" [--lang hi] [--lat .. --lng ..]` |
| A train booking's status | `pnr <10-digit PNR>` (sample data only) |

`--lang` is one of en, hi, kn, ta, te, bn. Use the language the user writes in.

## Planning

1. Run `plan` with the user's own words (cities, dates, who is going, budget, pace).
   It takes up to a minute; tell the user you are planning.
2. If the result has `needs_input`, ask the user those questions, then run `plan` again
   with the original text plus their answers.
3. Otherwise summarise `itinerary`: one line per day (`days[].date`, `days[].stops[].name`),
   the transport options (`transport[]`: mode, `total_minutes`, `total_cost_inr`), the
   budget (`budget.total_inr`), and any `warnings` and `season_notes` (quote them with
   their `source_url`). Give the `share_url` and keep `plan_id` for changes.

Revise intents (each returns a new `plan_id`; use the newest one next time):

- `lighter_day --day <date>`: fewer stops that day
- `rain [--day <date>]`: indoor stops (all days if no day)
- `swap_stop --place-id <id>`: replace a stop (`days[].stops[].id`)
- `move_day --city <destination>`: one more day in that city, taken from a neighbour
- `transport --mode rail`: travel by that mode throughout

## Stories and questions

- `katha` returns `text` with `[n]` markers; `sources[n-1]` is marker n. Keep the markers
  and list the sources. If `audio` is not empty, offer the chapter `url`s (MP3) in order.
  Hindi and Kannada stories are written natively; other languages come back in English,
  so translate them yourself if you can.
- `ask` returns `text` with `[n]` markers matching `citations`. For emergencies, pass the
  user's location as `--lat/--lng` if they shared it, list `emergency_places` with a map
  link, and always repeat 112 (and 108 for an ambulance).

## Rules

- Prices, timings and PNRs come only from the JSON. Never invent them.
- Never ask for card numbers, UPI ids, OTPs or passwords. Booking happens on the seller's
  site from the links in the plan.
- Travel Yantra is a prototype; say that fares and timings are estimates.

## Optional: the MCP server instead

When the Travel Yantra MCP server is public, OpenClaw can use its six tools directly
(`plan_trip`, `revise_trip`, `compare_transport`, `get_katha`, `ask_guide`, `track_booking`).
Add this to the OpenClaw config (see `{baseDir}/mcp.json`):

```json
{"mcp": {"servers": {"travel-yantra": {"url": "https://ty-mcp-643396702106.asia-south1.run.app/mcp", "transport": "streamable-http", "requestTimeoutMs": 180000}}}}
```
