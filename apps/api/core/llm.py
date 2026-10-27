"""Model access: the one place that reads model env vars.

`get_model()` returns the Gemini client, or the fake when TY_FAKE_LLM=1 (tests always use fakes).
"""

from __future__ import annotations

import os
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel

Tier = Literal["flash", "lite"]
M = TypeVar("M", bound=BaseModel)
TIMEOUT_MS = 20_000


def fake_enabled() -> bool:
    """TY_FAKE_LLM=1 selects the fake model: no model or network calls."""
    return os.getenv("TY_FAKE_LLM", "0") == "1"


def model_name(tier: Tier = "flash") -> str:
    if tier == "lite":
        return os.getenv("TY_MODEL_LITE", "gemini-3.1-flash-lite")
    return os.getenv("TY_MODEL_FLASH", "gemini-3.5-flash")


def backend() -> Literal["vertex", "ai_studio"]:
    """Vertex when GOOGLE_GENAI_USE_VERTEXAI is true (needs GOOGLE_CLOUD_PROJECT), else AI Studio (GEMINI_API_KEY)."""
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true"):
        if not os.getenv("GOOGLE_CLOUD_PROJECT"):
            raise RuntimeError("GOOGLE_CLOUD_PROJECT is required when GOOGLE_GENAI_USE_VERTEXAI is set")
        return "vertex"
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("set GEMINI_API_KEY, or GOOGLE_GENAI_USE_VERTEXAI with GOOGLE_CLOUD_PROJECT")
    return "ai_studio"


class Model(Protocol):
    async def json(self, prompt: str, schema: type[M], tier: Tier = "lite") -> M: ...
    async def text(self, prompt: str, tier: Tier = "flash") -> str: ...


class GeminiModel:
    """google-genai client. Vertex or AI Studio is chosen from the env by the client itself."""

    def __init__(self) -> None:
        from google import genai
        from google.genai import types

        backend()  # fail early with a clear message when nothing is configured
        self._types = types
        self._client = genai.Client(http_options=types.HttpOptions(timeout=TIMEOUT_MS))

    async def json(self, prompt: str, schema: type[M], tier: Tier = "lite") -> M:
        config = self._types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=schema, temperature=0
        )
        r = await self._client.aio.models.generate_content(model=model_name(tier), contents=prompt, config=config)
        return schema.model_validate_json(r.text)

    async def text(self, prompt: str, tier: Tier = "flash") -> str:
        config = self._types.GenerateContentConfig(temperature=0.6, max_output_tokens=600)
        r = await self._client.aio.models.generate_content(model=model_name(tier), contents=prompt, config=config)
        return (r.text or "").strip()


_model: Model | None = None


def get_model() -> Model:
    global _model
    if fake_enabled():
        from .fakes import FakeModel

        return FakeModel()
    if _model is None:
        _model = GeminiModel()
    return _model
