# apps/mcp (TY5 voice)

FastMCP server over streamable HTTP at `/mcp`. Tool: `plan_trip(request: TripRequest) -> Itinerary`.

- `API_BASE_URL` set: calls the API's `POST /plan` and returns the final itinerary.
- Not set: returns the Goa sample.

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
