import asyncio
import logging
import os
from collections.abc import Iterator
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ty_contracts import GuideAnswer, GuideQuestion, KathaStory

from .ask import Answerer, answerer, ask
from .katha import (
    LENGTHS_SERVED,
    KathaFailed,
    KathaRequest,
    UnknownSubject,
    katha,
    katha_model,
)
from .places import PgCache, PlacesClient

router = APIRouter(prefix="/guide")
log = logging.getLogger(__name__)
OFFLINE = "The guide is offline right now."
BUSY = "The guide couldn't answer just now. Try again in a minute."


def warm_up() -> None:
    """Called once at startup by main.py, in a background thread: load the query
    embedder so the first /guide/ask after a cold start doesn't pay 10-20 s for it.
    Idempotent; embed.model() loads once, and /ask waits on a load in progress."""
    from .planner import _pois
    from .retrieval import embed

    _pois()
    if os.environ.get("EMBEDDER") != "fake":
        embed.embed_query("warm up")  # loads the model and runs one encode


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


@router.get("/nearby")
async def get_nearby(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    kind: Literal["food", "veg", "atm", "pharmacy", "hospital"] = "food",
    limit: int = Query(3, ge=1, le=5),
    places: PlacesClient = Depends(get_places),
) -> list[dict]:
    """Help near a point for the live trip page (HQ P8): [{name, kind, lat, lng,
    distance_m, maps_url}], from Google Maps, cached a day."""
    from .ask import nearby_list

    try:
        return await asyncio.to_thread(nearby_list, places, lat, lng, kind, limit)
    except Exception as e:  # no key, quota, network
        log.exception("guide nearby failed")
        raise HTTPException(503, BUSY) from e


NO_STORY = "No story for that place yet."
NO_LONG_STORY = "10-minute stories aren't ready yet. Try the 5-minute story."


@router.get("/katha/library")
async def get_katha_library(lang: str | None = None, db: Any = Depends(get_db)) -> list[dict]:
    """Every place and city with a ready story (HQ P7): [{subject_kind, subject, city,
    lengths, langs, has_audio}], best-known first. `subject` is posted back as is."""
    from .katha.library import library

    try:
        items = await asyncio.to_thread(library, db)
    except Exception as e:  # katha_cache missing, a dropped connection
        log.exception("katha library failed")
        raise HTTPException(503, BUSY) from e
    return [i for i in items if not lang or lang in i["langs"]]


@router.post("/katha", response_model=KathaStory)
async def post_katha(
    req: KathaRequest,
    db: Any = Depends(get_db),
    model: Any = Depends(katha_model),
) -> KathaStory:
    if req.length_min not in LENGTHS_SERVED:
        raise HTTPException(404, NO_LONG_STORY)
    try:
        story = await katha(req, db, model)
    except UnknownSubject as e:
        raise HTTPException(404, NO_STORY) from e
    except KathaFailed as e:  # thin sources, or a draft that failed its checks twice
        log.warning("katha failed: %s", e.problems)
        raise HTTPException(503, BUSY) from e
    except Exception as e:
        log.exception("guide katha failed")
        raise HTTPException(503, BUSY) from e
    # Read aloud, if it has been (V3-AF): one small public GET; no audio is never an error.
    # Not yet: read on demand, a chapter a request, within the daily TTS cap (HQ P7).
    from .katha.ondemand import advance
    from .katha.voice import attach

    if audio := await asyncio.to_thread(attach, story):
        return story.model_copy(update={"audio": audio, "audio_status": "ready"})
    audio, status = await asyncio.to_thread(advance, story, db)
    return story.model_copy(update={"audio": audio, "audio_status": status})
