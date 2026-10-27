import asyncio
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ty_contracts import (
    Itinerary,
    PlanEvent,
    PlanStage,
    PlanText,
    ReviseRequest,
    TripRequest,
)

from .pipeline import revise_events, run_plan
from .revise import ReviseError, revise
from .trips import get_store

router = APIRouter()
# Seconds between SSE comment keepalives while a step is still running (Cloud Run drops idle streams).
PING_SECONDS = 15.0


@router.get("/health")
def health():
    return {"status": "ok", "version": os.getenv("GIT_SHA") or "dev"}


async def sse(events, ping: float = PING_SECONDS):
    """`data: <PlanEvent JSON>` frames, blank-line separated, with `: ping` comments while waiting."""
    it = aiter(events)
    pending = asyncio.ensure_future(anext(it))
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=ping)
            if not done:
                yield ": ping\n\n"
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            yield f"data: {event.model_dump_json(by_alias=True)}\n\n"
            pending = asyncio.ensure_future(anext(it))
    finally:
        pending.cancel()


def stream(events) -> StreamingResponse:
    return StreamingResponse(
        sse(events), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/plan")
async def plan(body: TripRequest | PlanText):
    """POST a TripRequest (form) or PlanText (free text). Streams PlanEvents as Server-Sent Events;
    the stream ends after the first done, needs_input or error event."""
    return stream(run_plan(body))


@router.post("/plan/{plan_id}/revise")
async def revise_plan(plan_id: str, body: ReviseRequest):
    """Lighter day, swap a stop, or a rain plan. 404 for an unknown plan, 422 when the day or stop is not
    in it; otherwise streams PlanEvents ending in done with a new plan_id (the old plan is kept)."""
    # Store calls (Postgres) and the solver are blocking; keep them off the event loop.
    trip = await asyncio.to_thread(lambda: get_store().get(plan_id))
    if trip is None:
        raise HTTPException(404, "plan not found")
    try:
        revised, what, rounds = await asyncio.to_thread(revise, trip.itinerary, body)
    except ReviseError as exc:
        raise HTTPException(422, str(exc)) from exc

    async def events():
        yield PlanEvent(stage=PlanStage.intake, message="Revising your plan…")
        for event in await asyncio.to_thread(revise_events, trip.id, revised, what, rounds):
            yield event

    return stream(events())


@router.get("/trips/{share_token}", response_model=Itinerary, response_model_by_alias=True)
def shared_trip(share_token: str) -> Itinerary:
    """Read-only shared trip. The token is the capability; there is no write path here."""
    trip = get_store().by_share_token(share_token)
    if trip is None:
        raise HTTPException(404, "trip not found")
    return trip.itinerary
