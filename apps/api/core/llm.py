"""Model access: the one place that reads model env vars. Real calls arrive in TY1-03."""

import os
from typing import Literal

Tier = Literal["flash", "lite"]


def fake_enabled() -> bool:
    """TY_FAKE_LLM=1 selects the fake agents: no model or network calls."""
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
