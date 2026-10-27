import datetime as dt
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from .compare import (
    CompareRequest,
    CompareResponse,
    CompareService,
    UnknownPlace,
    get_service,
)
from .irctc import (
    IrctcCard,
    NotFound,
    Party,
    PnrStatus,
    TravelClass,
    irctc_card,
    pnr_status,
)
from .metrics import (
    MAX_BODY_BYTES,
    MetricEvent,
    RateLimiter,
    Store,
    StoreFull,
    TaskSummary,
    client_ip,
    get_limiter,
    get_store,
    record,
    summarise,
)

router = APIRouter(prefix="/routes")


@router.post("/compare", response_model=CompareResponse)
def compare(req: CompareRequest, service: CompareService = Depends(get_service)) -> CompareResponse:
    try:
        return service.compare(req)
    except UnknownPlace as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/irctc-card", response_model=IrctcCard)
def get_irctc_card(
    from_: str = Query(alias="from", min_length=1),
    to: str = Query(min_length=1),
    date: dt.date = Query(),
    travel_class: TravelClass = "3A",
    party: Party = "goa_family",
    train: str | None = Query(default=None, pattern=r"^\d{5}$"),
) -> IrctcCard:
    try:
        return irctc_card(from_, to, date, travel_class, party, train)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/pnr-mock", response_model=PnrStatus)
def get_pnr_mock(pnr: str = Query(pattern=r"^\d{10}$"), at: dt.datetime | None = None) -> PnrStatus:
    try:
        return pnr_status(pnr, at)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/metrics/event", status_code=201)
async def post_metric_event(request: Request, store: Store = Depends(get_store),
                            limiter: RateLimiter = Depends(get_limiter)) -> dict:
    ip = client_ip(request.headers.get("x-forwarded-for"), request.client.host if request.client else None)
    if not limiter.allow(ip):
        raise HTTPException(status_code=429, detail="too many events; try again in a minute")
    # Parse JSON whatever the content type: navigator.sendBeacon sends text/plain.
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="event too large")
    try:
        event = MetricEvent.model_validate(json.loads(body))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="body must be JSON") from exc
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False, include_context=False)) from exc
    try:
        await run_in_threadpool(record, store, event)  # psycopg is blocking
    except StoreFull as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/metrics/summary", response_model=list[TaskSummary])
def get_metric_summary(store: Store = Depends(get_store)) -> list[TaskSummary]:
    return summarise(store.all())
