import logging
import os
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ty_contracts import GuideAnswer, GuideQuestion, KathaStory

from .ask import Answerer, answerer, ask
from .katha import KathaFailed, KathaRequest, UnknownSubject, katha, katha_model
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


NO_STORY = "No story for that place yet."


@router.post("/katha", response_model=KathaStory)
async def post_katha(
    req: KathaRequest,
    db: Any = Depends(get_db),
    model: Any = Depends(katha_model),
) -> KathaStory:
    try:
        return await katha(req, db, model)
    except UnknownSubject as e:
        raise HTTPException(404, NO_STORY) from e
    except KathaFailed as e:  # thin sources, or a draft that failed its checks twice
        log.warning("katha failed: %s", e.problems)
        raise HTTPException(503, BUSY) from e
    except Exception as e:
        log.exception("guide katha failed")
        raise HTTPException(503, BUSY) from e
