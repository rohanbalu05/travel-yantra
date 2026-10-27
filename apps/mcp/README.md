# apps/mcp (TY5 voice)

FastMCP server over streamable HTTP at `/mcp`. Six tools:

| Tool | API call | Returns |
| --- | --- | --- |
| `plan_trip(request)` | `POST /plan` (SSE PlanEvents) | `{plan_id, itinerary, share_url}` |
| `compare_transport(origin, destination, on?, rank_by, travellers)` | `POST /routes/compare` | `CompareResponse` |
| `revise_trip(plan_id, intent, day?, place_id?, lang)` | `POST /plan/{id}/revise` (SSE) | `{plan_id, itinerary, share_url}` |
| `get_katha(subject, subject_kind, length_min, lang, places?)` | `POST /guide/katha` | `KathaStory` |
| `ask_guide(question, lang, lat?, lng?)` | `POST /guide/ask` | `GuideAnswer` |
| `track_booking(pnr)` | `GET /routes/pnr-mock` | PNR timeline (mock) |

- `API_BASE_URL` set: each tool calls the API.
- Not set: each tool answers from `samples/` (the Goa sample and `offline.json`).
- `TRANSLATE_URL` set: `ask_guide` and `get_katha` text is translated to `lang` by services/translate, with
  `[n]` citation markers kept (`[n]` is `citations[n-1]`). Unset, or a flagged translation: English.

## Run

```
cd apps/mcp && uv run python server.py   # http://localhost:8080/mcp
```

## Add to an MCP client

```json
{ "mcpServers": { "travel-yantra": { "url": "http://localhost:8080/mcp" } } }
```

Clients with an add command, for example: `<client> mcp add --transport http travel-yantra http://localhost:8080/mcp`

## Test

```
cd apps/mcp && uv run pytest
```
