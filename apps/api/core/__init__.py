import os

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from ty_contracts import TripRequest

from .pipeline import run_plan

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "version": os.getenv("GIT_SHA") or "dev"}


@router.post("/plan")
async def plan(request: TripRequest):
    """Server-Sent Events: one `data: <PlanEvent JSON>` frame per event, blank-line separated."""

    async def frames():
        async for event in run_plan(request):
            yield f"data: {event.model_dump_json(by_alias=True)}\n\n"

    return StreamingResponse(
        frames(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
