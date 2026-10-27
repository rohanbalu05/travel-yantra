"""Travel Yantra MCP server: streamable HTTP at /mcp.

Every tool calls the API at API_BASE_URL; without it, tools answer from samples/.
"""

import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
from ty_contracts import (
    CityRef,
    CompareRequest,
    CompareResponse,
    GuideAnswer,
    GuideQuestion,
    Itinerary,
    KathaRequest,
    KathaStory,
    Lang,
    PlanEvent,
    PlanStage,
    RankedOption,
    TripRequest,
)

from translate import Translator

SAMPLE = Path(__file__).parent / "samples/goa_family.json"
OFFLINE = Path(__file__).parent / "samples/offline.json"

SAMPLE_PLAN_ID = "sample-goa"


class PlannedTrip(BaseModel):
    """A plan and its id; pass plan_id to revise_trip. share_url is a read-only link to it."""

    plan_id: str | None
    itinerary: Itinerary
    share_url: str | None = None


def share_url(token: str | None) -> str | None:
    """TY4's web page {SHARE_BASE_URL}/t/{token}/, else the API's JSON for the same plan."""
    if not token:
        return None
    web = os.environ.get("SHARE_BASE_URL", "").rstrip("/")
    return f"{web}/t/{quote(token, safe='')}/" if web else f"{_base()}/trips/{quote(token, safe='')}"


mcp = FastMCP("travel-yantra", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))


def _base() -> str | None:
    base = os.environ.get("API_BASE_URL")
    return base.rstrip("/") if base else None


def _sample_itinerary() -> Itinerary:
    return Itinerary.model_validate(json.loads(SAMPLE.read_text(encoding="utf-8"))["itinerary"])


def _offline(key: str) -> Any:
    return json.loads(OFFLINE.read_text(encoding="utf-8"))[key]


async def _request(method: str, path: str, timeout: float = 60, **kw: Any) -> Any:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(method, f"{_base()}{path}", **kw)
        _raise_for_detail(resp)
        return resp.json()


def _raise_for_detail(resp: httpx.Response) -> None:
    """On an error, raise with the API's own words ("unknown sample PNR", a 422's messages)."""
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail")
        except ValueError:
            detail = None
        if isinstance(detail, list):  # FastAPI validation errors
            detail = "; ".join(str(d.get("msg", d)) for d in detail if isinstance(d, dict)) or None
        if isinstance(detail, str):
            raise RuntimeError(detail)
    resp.raise_for_status()


async def _stream_plan(path: str, body: Any) -> PlannedTrip:
    final, plan_id, token = None, None, None
    async with (
        httpx.AsyncClient(timeout=120) as client,
        client.stream("POST", f"{_base()}{path}", json=body) as resp,
    ):
        if resp.is_error:
            await resp.aread()
        _raise_for_detail(resp)
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            event = PlanEvent.model_validate_json(line[5:].strip())
            if event.stage == PlanStage.error:
                raise RuntimeError(event.message)
            if event.stage == PlanStage.needs_input:
                raise RuntimeError("The planner needs more details: " + " ".join(event.questions))
            if event.partial is not None:
                final = event.partial
            if event.stage == PlanStage.done:
                plan_id, token = event.plan_id, event.share_token
                break
    if final is None:
        raise RuntimeError("plan finished without an itinerary")
    return PlannedTrip(plan_id=plan_id, itinerary=final, share_url=share_url(token))


@mcp.tool()
async def plan_trip(request: TripRequest) -> PlannedTrip:
    """Plan a multi-city trip in India; returns the itinerary and a plan_id for revise_trip."""
    if not _base():
        return PlannedTrip(plan_id=SAMPLE_PLAN_ID, itinerary=_sample_itinerary())
    return await _stream_plan("/plan", json.loads(request.model_dump_json()))


@mcp.tool()
async def compare_transport(
    origin: str,
    destination: str,
    on: date | None = None,
    rank_by: Literal["balanced", "time", "cost", "changes"] = "balanced",
    travellers: int = 1,
) -> CompareResponse:
    """Compare door-to-door flight, rail and road options for one leg, ranked, with prices and links.

    `unavailable` says which modes have no option and why.
    """
    req = CompareRequest(
        origin=origin, destination=destination, date=on, rank_by=rank_by, travellers=travellers
    )
    if not _base():
        return _sample_compare(req)
    data = await _request("POST", "/routes/compare", json=req.model_dump(mode="json"))
    return CompareResponse.model_validate(data)


def _sample_compare(req: CompareRequest) -> CompareResponse:
    it = _sample_itinerary()
    ranked = [
        RankedOption(
            id=f"sample-{i}", rank=i, changes=len(o.legs) - 1, score=0, sources=["sample"], option=o
        )
        for i, o in enumerate(it.transport, start=1)
    ]
    return CompareResponse(
        origin=CityRef(name="Bengaluru", lat=12.9716, lng=77.5946),
        destination=CityRef(name="Goa", lat=15.4909, lng=73.8278),
        date=req.date or it.request.start_date,
        rank_by=req.rank_by,
        options=ranked,
        notes=["offline sample: Bengaluru to Goa, whatever was asked"],
    )


@mcp.tool()
async def revise_trip(
    plan_id: str,
    intent: Literal["lighter_day", "swap_stop", "rain"],
    day: date | None = None,
    place_id: str | None = None,
    lang: Lang = Lang.en,
) -> PlannedTrip:
    """Revise a planned trip (plan_id from plan_trip): lighter day, swap a stop, or rain plan.

    lighter_day needs day; swap_stop needs place_id; rain without a day covers every day.
    Returns a new plan_id; the old plan stays revisable.
    """
    if not _base():
        it = _sample_itinerary()
        it = it.model_copy(update={"warnings": [*it.warnings, "offline sample: not revised"]})
        return PlannedTrip(plan_id=plan_id, itinerary=it)
    body = {"intent": intent, "day": day.isoformat() if day else None, "place_id": place_id}
    body = {k: v for k, v in body.items() if v is not None} | {"lang": lang.value}
    return await _stream_plan(f"/plan/{quote(plan_id, safe='')}/revise", body)


@mcp.tool()
async def get_katha(
    subject: str,
    subject_kind: Literal["place", "city", "day"] = "place",
    length_min: Literal[2, 5, 10] = 2,
    lang: Lang = Lang.en,
    places: list[str] | None = None,
) -> KathaStory:
    """Tell the story (Katha) of a place, a city or a trip day in 2, 5 or 10 minutes.

    subject: a place name or id slug (e.g. "mysuru-mysore-palace"), a city name, or for a day a
    label with its `places`. Segments are labelled legend, history or disputed (sources
    disagree); [n] is sources[n-1].
    A first telling can take up to a minute.
    """
    if not _base():
        story = KathaStory.model_validate(_offline("katha"))
    else:
        req = KathaRequest(
            subject_kind=subject_kind,
            subject=subject,
            length_min=length_min,
            lang=Lang.en,  # the guide writes English; translation happens here
            places=places or [],
        )
        body = req.model_dump(mode="json", exclude={"places"} if subject_kind != "day" else None)
        data = await _request("POST", "/guide/katha", timeout=90, json=body)
        story = KathaStory.model_validate(data)
    # One translate call for the text and every segment; Translator.text keeps the line count.
    items = [story.text, *(s.text for s in story.segments)]
    lines = (await Translator().text("\n".join(items), lang)).split("\n")
    outs = []
    for item in items:
        n = item.count("\n") + 1
        outs.append("\n".join(lines[:n]))
        lines = lines[n:]
    if outs[0] == story.text:
        return story  # English, or translation unavailable
    segs = [s.model_copy(update={"text": t}) for s, t in zip(story.segments, outs[1:])]
    return story.model_copy(update={"text": outs[0], "segments": segs, "lang": lang})


@mcp.tool()
async def ask_guide(
    question: str, lang: Lang = Lang.en, lat: float | None = None, lng: float | None = None
) -> GuideAnswer:
    """Ask the travel guide about history, food, culture or emergencies; answers cite sources.

    [n] in the text is citations[n-1]. Pass lat/lng for emergencies (hospital, police, pharmacy).
    """
    if not _base():
        answer = GuideAnswer.model_validate(_offline("guide"))
    else:
        q = GuideQuestion(question=question, lang=lang, lat=lat, lng=lng)
        body = q.model_dump(mode="json", exclude_none=True)
        answer = GuideAnswer.model_validate(await _request("POST", "/guide/ask", json=body))
    # The guide answers in English; only the text is translated, [n] markers kept.
    text = await Translator().text(answer.text, lang)
    if text == answer.text:
        return answer
    return answer.model_copy(update={"text": text, "lang": lang})


@mcp.tool()
async def track_booking(pnr: str) -> dict[str, Any]:
    """Track a train booking by PNR (mock timeline from sample data; there is no IRCTC API)."""
    if not _base():
        return _offline("pnr")
    return await _request("GET", "/routes/pnr-mock", params={"pnr": pnr})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
