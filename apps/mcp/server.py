"""Travel Yantra MCP server: streamable HTTP at /mcp.

Every tool calls the API at API_BASE_URL; without it, tools answer from samples/.
"""

import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from ty_contracts import (
    GuideAnswer,
    Itinerary,
    KathaStory,
    Lang,
    PlanEvent,
    PlanStage,
    TransportOption,
    TripRequest,
)

SAMPLE = Path(__file__).parent / "samples/goa_family.json"
OFFLINE = Path(__file__).parent / "samples/offline.json"

mcp = FastMCP("travel-yantra", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))


def _base() -> str | None:
    base = os.environ.get("API_BASE_URL")
    return base.rstrip("/") if base else None


def _sample_itinerary() -> Itinerary:
    return Itinerary.model_validate(json.loads(SAMPLE.read_text(encoding="utf-8"))["itinerary"])


def _offline(key: str) -> Any:
    return json.loads(OFFLINE.read_text(encoding="utf-8"))[key]


async def _request(method: str, path: str, **kw: Any) -> Any:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.request(method, f"{_base()}{path}", **kw)
        resp.raise_for_status()
        return resp.json()


async def _stream_plan(path: str, body: Any) -> Itinerary:
    final = None
    async with (
        httpx.AsyncClient(timeout=120) as client,
        client.stream("POST", f"{_base()}{path}", json=body) as resp,
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


@mcp.tool()
async def plan_trip(request: TripRequest) -> Itinerary:
    """Plan a multi-city trip in India and return the final itinerary."""
    if not _base():
        return _sample_itinerary()
    return await _stream_plan("/plan", json.loads(request.model_dump_json()))


@mcp.tool()
async def compare_transport(origin: str, destination: str, on: date) -> list[TransportOption]:
    """Compare door-to-door flight, rail and road options for one leg, with prices and links."""
    if not _base():
        return _sample_itinerary().transport
    # ponytail: assumes POST /routes/compare takes {origin, destination, date} (card #25)
    data = await _request(
        "POST",
        "/routes/compare",
        json={"origin": origin, "destination": destination, "date": on.isoformat()},
    )
    return [TransportOption.model_validate(o) for o in data]


@mcp.tool()
async def revise_trip(
    plan_id: str,
    intent: Literal["lighter_day", "swap_stop", "rain"],
    day: date | None = None,
    place_id: str | None = None,
) -> Itinerary:
    """Revise a planned trip: make a day lighter, swap a stop, or re-plan a day for rain."""
    if not _base():
        it = _sample_itinerary()
        return it.model_copy(update={"warnings": [*it.warnings, "offline sample: not revised"]})
    body = {"intent": intent, "day": day.isoformat() if day else None, "place_id": place_id}
    return await _stream_plan(f"/plan/{plan_id}/revise", body)


@mcp.tool()
async def get_katha(place_id: str, length: Literal[2, 5, 10] = 2) -> KathaStory:
    """Tell the story (Katha) of a place in 2, 5 or 10 minutes, legend and history labelled."""
    if not _base():
        return KathaStory.model_validate(_offline("katha"))
    data = await _request("GET", "/guide/katha", params={"place_id": place_id, "length": length})
    return KathaStory.model_validate(data)


@mcp.tool()
async def ask_guide(question: str, lang: Lang = Lang.en) -> GuideAnswer:
    """Ask the travel guide about history, food, culture or emergencies; answers cite sources."""
    if not _base():
        return GuideAnswer.model_validate(_offline("guide"))
    # ponytail: assumes POST /guide/ask takes {question, lang} (card #23)
    data = await _request("POST", "/guide/ask", json={"question": question, "lang": lang})
    return GuideAnswer.model_validate(data)


@mcp.tool()
async def track_booking(pnr: str) -> dict[str, Any]:
    """Track a train booking by PNR (mock timeline from sample data; there is no IRCTC API)."""
    if not _base():
        return _offline("pnr")
    return await _request("GET", "/routes/pnr-mock", params={"pnr": pnr})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
