"""FastAPI app: POST /translate, GET /health."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .service import TranslationService
from .translator import FakeTranslator, IndicTrans2Translator, Lang, Translator


class TranslateRequest(BaseModel):
    texts: list[str] = Field(max_length=200)
    target: Lang
    source: Literal["en"] = "en"


class TranslateResponse(BaseModel):
    translations: list[str]
    target: Lang


def build_translator() -> Translator:
    if os.environ.get("TY_FAKE_TRANSLATOR", "1") == "1":
        return FakeTranslator()
    return IndicTrans2Translator()


def create_app(service: TranslationService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Model is loaded once, here, not per request.
        app.state.service = service or TranslationService(
            build_translator(),
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
        out = app.state.service.translate(req.texts, req.target, req.source)
        return TranslateResponse(translations=out, target=req.target)

    return app


app = create_app()
