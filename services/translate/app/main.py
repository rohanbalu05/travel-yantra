"""FastAPI app: POST /translate, GET /health."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .service import TranslationService
from .translator import FakeTranslator, IndicTrans2Translator, Lang, Translator


class TranslateRequest(BaseModel):
    # Each text is capped (about 256 output tokens); split long paragraphs into sentences first.
    texts: list[Annotated[str, Field(max_length=1000)]] = Field(max_length=200)
    target: Lang
    source: Literal["en"] = "en"
    # Place names that appear in the texts; kept out of the model and shown in their native form.
    entities: list[str] = Field(default_factory=list, max_length=50)


class TranslateResponse(BaseModel):
    translations: list[str]
    target: Lang
    via: list[str]  # per text: "phrasebook" or "model"
    flags: list[list[str]]  # per text: wrong_script, length, entity_lost:<name>


def build_translator() -> Translator:
    if os.environ.get("TY_FAKE_TRANSLATOR", "1") == "1":
        return FakeTranslator()
    return IndicTrans2Translator()


def load_entity_names() -> dict[str, dict[str, str]]:
    """Native place names ({"Hampi": {"hi": "..."}}) from TY_ENTITY_NAMES_FILE, if set."""
    path = os.environ.get("TY_ENTITY_NAMES_FILE")
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else {}


def create_app(service: TranslationService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Model is loaded once, here, not per request.
        app.state.service = service or TranslationService(
            build_translator(),
            entity_names=load_entity_names(),
            max_batch=int(os.environ.get("TY_MAX_BATCH", "16")),
            cache_size=int(os.environ.get("TY_CACHE_SIZE", "4096")),
        )
        yield

    app = FastAPI(title="ty-translate", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/translate", response_model=TranslateResponse)
    def translate(req: TranslateRequest) -> TranslateResponse:
        out = app.state.service.translate_checked(req.texts, req.target, req.source, req.entities)
        return TranslateResponse(
            translations=[r.text for r in out],
            target=req.target,
            via=[r.via for r in out],
            flags=[r.flags for r in out],
        )

    return app


app = create_app()
