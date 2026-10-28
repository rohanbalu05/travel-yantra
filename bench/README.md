# TY-Bench

Travel Yantra's planner (`/plan` on the live ty-api) against one plain Gemini
3.5 Flash prompt, on 30 fixed requests across the four regions: Karnataka, Goa,
Kerala and the Golden Triangle. The personas are families, seniors, shoestring,
luxury and monsoon (rain). Every traveller is the sample persona (Arjun Rao and
family).

Cities match the guide corpus. On 28 Oct, b27 changed from Thiruvananthapuram
(no places loaded) to Kochi to Munnar, and b26 now spells Alappuzha the corpus
way, "Alleppey".

| File | What it is |
| --- | --- |
| `requests.jsonl` | the 30 requests: id, region, persona, the words a traveller would type, and the TripRequest |
| `tybench.py` | runs both arms, scores them, writes `results/<run>.jsonl`, prints a summary |
| `score.py` | the scoring, pure (no network, no model) |
| `test_score.py` | tests for the scoring on the contracts' sample plan |
| `prices.json` | Vertex prices per 1M tokens, with source and date, for ₹ per plan |

## Run

```
cd apps/api
uv run pytest ../../bench -q                         # scoring tests, offline
uv run python ../../bench/tybench.py --dry-run       # first 3 requests, both arms (live calls)
uv run python ../../bench/tybench.py --full          # all 30: only after HQ's freeze
uv run python ../../bench/score.py ../../bench/results/<run>.jsonl   # score a run again
```

The baseline calls Vertex AI with Application Default Credentials on the trial
project (`GOOGLE_CLOUD_PROJECT`; the script sets `GOOGLE_GENAI_USE_VERTEXAI` and
`GOOGLE_CLOUD_LOCATION=global` if unset). The ty arm's tokens come from
ty-api's own usage lines in Cloud Logging, in each request's time window, so it
needs `gcloud` (TY6). Pass `--no-logs` to skip them. A full run is about 300
Flash calls on the trial credit.

## Scoring

Each plan passes or fails each dimension. A plan that doesn't parse as an
Itinerary fails all of them. Plans are scored against the request that was
asked, never the copy inside the plan.

| Dimension | Pass when |
| --- | --- |
| valid | it parses as a `ty_contracts` Itinerary |
| dates | one day per date, start to end |
| hours | TY1's `core.checker.check`: no `closed` |
| travel_time | no `too_much_travel` |
| constraints | no `long_day`, no `no_rest` (elders) |
| budget | no `over_budget` (total from `core.checker.budget`) |
| meals | bench's own check: each day with stops has a food stop or 45 free minutes between 12:00 and 14:30 |

The checker uses haversine road times (its default), so scoring makes no live
calls. TY1's checker has no meal rule; the meal check is the bench's and is
applied to both arms the same way.

## Guide latency (TY2)

`guide.scripts.bench_ask` times `/guide/ask` (retrieval and model, p50 and
p95). It needs Cloud SQL, so it runs as the Cloud Run job `ty-bench-ask` (the
ty-api image, as ty-api-run, with `DATABASE_URL` from Secret Manager):
`gcloud run jobs execute ty-bench-ask --region asia-south1 --wait`. Update its
image to ty-api's live one first (`gcloud run jobs update ty-bench-ask --image …`).

Dry run, 28 Oct, image 5bfee23, `bench_ask 3` (the eval set is now
`guide/eval/eval_ask.jsonl`, shipped in the image): p50 2.03 s, p95 2.43 s,
retrieval p95 0.12 s, 3 of 3 cited. The questions were the battle of
Talikota, when Mysore Palace burned, and Tipu Sultan's summer palace.

## Dry run, 28 Oct 2026 (3 requests: Mysuru with a family, seniors, shoestring)

| Arm | valid | dates | hours | travel | meals | budget | constraints | p50 s | p95 s | tokens/plan | ₹/plan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ty | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 3/3 | 3/3 | 9.8 | 18.6 | 208 | ~0.02 |
| baseline | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 3/3 | 2/3 | 35.7 | 73.3 | 13,258 | 8.04 |

`results/20261028-151328-dry.jsonl`. Notes:

- The ty arm's ₹ was worked out afterwards, from the one Flash-Lite call in its
  window (55 in, 148 out). The Flash-Lite price wasn't in `prices.json` yet
  during the run.
- Neither arm leaves time for lunch on every day (sent to TY1).
- Three requests is too few to compare. The full run waits for the freeze.
- Prices are provisional (see `prices.json`). The pricing docs say
  gemini-3.5-flash requests may be routed to a newer Flash.
