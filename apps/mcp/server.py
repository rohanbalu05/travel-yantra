"""Travel Yantra MCP server: streamable HTTP at /mcp."""

import json
import os
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP
from ty_contracts import Itinerary, PlanEvent, PlanStage, TripRequest

SAMPLE = Path(__file__).resolve().parents[2] / "packages/contracts/samples/goa_family.json"

mcp = FastMCP("travel-yantra", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))


@mcp.tool()
async def plan_trip(request: TripRequest) -> Itinerary:
    """Plan a multi-city trip in India and return the final itinerary."""
    base = os.environ.get("API_BASE_URL")
    if not base:
        return Itinerary.model_validate(json.loads(SAMPLE.read_text(encoding="utf-8"))["itinerary"])
    final = None
    async with (
        httpx.AsyncClient(timeout=120) as client,
        client.stream(
            "POST", f"{base.rstrip('/')}/plan", json=json.loads(request.model_dump_json())
        ) as resp,
    ):
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            # ponytail: assumes /plan streams SSE `data: <PlanEvent json>` lines
            if not line.startswith("data:"):
                continue
            event = PlanEvent.model_validate_json(line[5:].strip())
            if event.stage == PlanStage.error:
                raise RuntimeError(event.message)
            if event.partial is not None:
                final = event.partial
            if event.stage == PlanStage.done:
                break
    if final is None:
        raise RuntimeError("plan finished without an itinerary")
    return final


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
