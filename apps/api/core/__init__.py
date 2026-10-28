import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse

from ty_contracts import (
    Itinerary,
    PlanEvent,
    PlanStage,
    PlanText,
    ReviseRequest,
    SavedPlan,
    TripRequest,
)

from .accounts import caller_ids, client_id, creator_key, get_accounts, keeps_history
from .accounts import router as accounts_router
from .checker import settled
from .pipeline import revise_events, run_plan
from .revise import ReviseError, revise
from .trips import get_store

log = logging.getLogger("core.pipeline")
router = APIRouter()
router.include_router(accounts_router)
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
async def plan(body: TripRequest | PlanText, client: str | None = Depends(client_id)):
    """POST a TripRequest (form) or PlanText (free text). Streams PlanEvents as Server-Sent Events;
    the stream ends after the first done, needs_input or error event. With X-Client-Id and the plan_history
    consent, the finished trip is listed in /me/trips."""
    return stream(run_plan(body, client))


def _own(plan_id: str, client: str | None, ids: tuple[str, ...] = ()):
    """The trip, if the caller may change it: a trip with an owner needs that caller; one without needs the
    browser, chat or account that made it (older trips without a maker: whoever holds the plan_id). 404 and
    403 say so in a plain sentence."""
    trip = get_store().get(plan_id)
    if trip is None:
        raise HTTPException(404, "This plan was not found. It may have been deleted.")
    if trip.owner is not None and trip.owner != client:
        raise HTTPException(403, "This plan belongs to someone else.")
    if trip.owner is None and trip.creator and trip.creator not in {creator_key(c) for c in (*ids, client) if c}:
        raise HTTPException(403, "Only the browser or chat that made this plan can change it. "
                                 "Its share link still shows it.")
    return trip


@router.get("/plan/{plan_id}", response_model=SavedPlan, response_model_by_alias=True)
def get_plan(plan_id: str, client: str | None = Depends(client_id), ids: tuple[str, ...] = Depends(caller_ids)) -> SavedPlan:
    """The latest version of a trip, to reopen it editable. Same rules as revise: 404, or 403 for a trip
    that belongs to another account or browser."""
    trip = _own(plan_id, client, ids)
    return SavedPlan(plan_id=trip.id, share_token=trip.share_token, itinerary=settled(trip.itinerary, log),
                     version=trip.version, updated_at=trip.changed_at)


@router.post("/plan/{plan_id}/revise")
async def revise_plan(plan_id: str, body: ReviseRequest, client: str | None = Depends(client_id),
                      ids: tuple[str, ...] = Depends(caller_ids)):
    """Apply one change. 404 for an unknown plan, 403 for someone else's, 422 when the change does not fit
    it; otherwise streams PlanEvents ending in done with the same plan_id and share_token (a new version)."""
    # Store calls (Postgres) and the solver are blocking; keep them off the event loop.
    trip = await asyncio.to_thread(_own, plan_id, client, ids)
    try:
        revised, what, rounds = await asyncio.to_thread(revise, settled(trip.itinerary, log), body)
    except ReviseError as exc:
        raise HTTPException(422, str(exc)) from exc

    async def events():
        yield PlanEvent(stage=PlanStage.intake, message="Revising your plan…")
        owner = client if client and await asyncio.to_thread(keeps_history, client) else None
        for event in await asyncio.to_thread(revise_events, trip.id, revised, what, rounds, owner, trip.version):
            yield event

    return stream(events())


@router.delete("/plan/{plan_id}", status_code=204)
def delete_plan(plan_id: str, client: str | None = Depends(client_id), ids: tuple[str, ...] = Depends(caller_ids)) -> Response:
    """Delete one plan by its id (the creator's capability; a share token is not enough). A plan linked to an
    account or browser needs that caller (403 otherwise). Its share link stops working; ratings of it go too."""
    _own(plan_id, client, ids)
    get_store().delete(plan_id)
    get_accounts().delete_ratings_for([plan_id])
    return Response(status_code=204)


@router.get("/trips/{share_token}", response_model=Itinerary, response_model_by_alias=True)
def shared_trip(share_token: str) -> Itinerary:
    """Read-only shared trip. The token is the capability; there is no write path here."""
    trip = get_store().by_share_token(share_token)
    if trip is None:
        raise HTTPException(404, "trip not found")
    return settled(trip.itinerary, log)
