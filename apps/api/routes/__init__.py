from fastapi import APIRouter, Depends, HTTPException

from .compare import (
    CompareRequest,
    CompareResponse,
    CompareService,
    UnknownPlace,
    get_service,
)

router = APIRouter(prefix="/routes")


@router.post("/compare", response_model=CompareResponse)
def compare(req: CompareRequest, service: CompareService = Depends(get_service)) -> CompareResponse:
    try:
        return service.compare(req)
    except UnknownPlace as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
