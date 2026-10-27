import asyncio
import os

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ty_contracts import PlanText, TripRequest

from .pipeline import run_plan

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


@router.post("/plan")
async def plan(body: TripRequest | PlanText):
    """POST a TripRequest (form) or PlanText (free text). Streams PlanEvents as Server-Sent Events;
    the stream ends after the first done, needs_input or error event."""
    return StreamingResponse(
        sse(run_plan(body)), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
