import logging
import os
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ty_contracts import GuideAnswer, GuideQuestion

from .ask import Answerer, answerer, ask
from .places import PgCache, PlacesClient

router = APIRouter(prefix="/guide")
log = logging.getLogger(__name__)
OFFLINE = "The guide is offline right now."
BUSY = "The guide couldn't answer just now. Try again in a minute."


def get_db() -> Iterator[Any]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise HTTPException(503, OFFLINE)
    import psycopg

    try:
        conn = psycopg.connect(url, autocommit=True, connect_timeout=5)
    except psycopg.OperationalError as e:
        raise HTTPException(503, OFFLINE) from e
    with conn:
        yield conn


def get_places(db: Any = Depends(get_db)) -> PlacesClient:
    return PlacesClient(cache=PgCache(db))


@router.post("/ask", response_model=GuideAnswer)
async def post_ask(
    req: GuideQuestion,
    db: Any = Depends(get_db),
    model: Answerer = Depends(answerer),
    places: PlacesClient = Depends(get_places),
) -> GuideAnswer:
    try:
        return await ask(req, db, model, places)
    except Exception as e:  # model quota or timeout, embedder missing, a dropped connection
        log.exception("guide ask failed")
        raise HTTPException(503, BUSY) from e
