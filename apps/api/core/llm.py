"""Model access: the one place that reads model env vars.

`get_model()` returns the Gemini client, or the fake when TY_FAKE_LLM=1 (tests always use fakes).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel

Tier = Literal["flash", "lite"]
# Gemini 3.x thinks by default and thinking tokens count toward max_output_tokens; pick a level per call.
Thinking = Literal["minimal", "low", "medium", "high"]
M = TypeVar("M", bound=BaseModel)
TIMEOUT_MS = 20_000
# Retry on quota (429) and overload (503): at most 3 tries, all within 20 s including the calls themselves.
RETRY_CODES = (429, 503)
MAX_TRIES = 3
RETRY_BUDGET_S = 20.0
BACKOFF_BASE_S = 1.0

log = logging.getLogger(__name__)
_now = time.monotonic  # patched in tests


def log_usage(model: str, response, label: str | None, seconds: float) -> None:
    """One INFO line per successful call: model, label and token counts (missing counts are 0). No prompt text."""
    u = getattr(response, "usage_metadata", None)
    n = {k: (getattr(u, k, None) or 0) for k in ("prompt_token_count", "candidates_token_count",
                                                 "thoughts_token_count", "total_token_count")}
    log.info("model=%s label=%s prompt=%d output=%d thoughts=%d total=%d seconds=%.2f", model, label or "-",
             n["prompt_token_count"], n["candidates_token_count"], n["thoughts_token_count"], n["total_token_count"],
             seconds)


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
    async def json(self, prompt: str, schema: type[M], tier: Tier = "lite", *, thinking: Thinking | None = None,
                   timeout_s: float | None = None, label: str | None = None) -> M: ...

    async def text(self, prompt: str, tier: Tier = "flash", *, thinking: Thinking | None = None,
                   max_output_tokens: int = 600, temperature: float = 0.6, timeout_s: float | None = None,
                   label: str | None = None) -> str: ...


class GeminiModel:
    """google-genai client. Vertex or AI Studio is chosen from the env by the client itself."""

    def __init__(self) -> None:
        from google import genai
        from google.genai import types

        backend()  # fail early with a clear message when nothing is configured
        self._types = types
        self._client = genai.Client(http_options=types.HttpOptions(timeout=TIMEOUT_MS))

    def _thinking(self, level: Thinking | None):
        return self._types.ThinkingConfig(thinking_level=level.upper()) if level else None

    async def json(self, prompt: str, schema: type[M], tier: Tier = "lite", *, thinking: Thinking | None = None,
                   timeout_s: float | None = None, label: str | None = None) -> M:
        config = self._types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=schema, temperature=0,
            thinking_config=self._thinking(thinking),
        )
        r = await self._generate(model_name(tier), prompt, config, timeout_s, label or schema.__name__)
        return schema.model_validate_json(r.text)

    async def text(self, prompt: str, tier: Tier = "flash", *, thinking: Thinking | None = None,
                   max_output_tokens: int = 600, temperature: float = 0.6, timeout_s: float | None = None,
                   label: str | None = None) -> str:
        config = self._types.GenerateContentConfig(
            temperature=temperature, max_output_tokens=max_output_tokens, thinking_config=self._thinking(thinking)
        )
        r = await self._generate(model_name(tier), prompt, config, timeout_s, label)
        return (r.text or "").strip()

    async def _generate(self, model: str, prompt: str, config, timeout_s: float | None = None, label: str | None = None):
        """generate_content with retries on 429 and 503: exponential backoff with full jitter, each try
        capped to the time left in the budget (timeout_s, default RETRY_BUDGET_S). Other errors, and the
        last failure, are raised."""
        from google.genai import errors

        budget = timeout_s or RETRY_BUDGET_S
        start = _now()
        for attempt in range(1, MAX_TRIES + 1):
            left = budget - (_now() - start)
            config.http_options = self._types.HttpOptions(timeout=int(max(left, 1) * 1000))
            try:
                r = await self._client.aio.models.generate_content(model=model, contents=prompt, config=config)
                log_usage(model, r, label, _now() - start)
                return r
            except errors.APIError as exc:
                if exc.code not in RETRY_CODES or attempt == MAX_TRIES:
                    raise
                wait = random.uniform(0, BACKOFF_BASE_S * 2 ** (attempt - 1))
                left = budget - (_now() - start)
                if wait >= left - 1:  # leave at least a second for the next try
                    raise
                log.warning("model %s returned %s; retry %d of %d in %.1f s", model, exc.code, attempt, MAX_TRIES - 1, wait)
                await asyncio.sleep(wait)


_model: Model | None = None


def get_model() -> Model:
    global _model
    if fake_enabled():
        from .fakes import FakeModel

        return FakeModel()
    if _model is None:
        _model = GeminiModel()
    return _model
