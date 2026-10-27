"""Translator interface, a deterministic fake, Gemini (the default live path) and IndicTrans2 (off)."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Literal, Protocol

Lang = Literal["hi", "kn", "ta", "te", "bn"]
LANGS: tuple[str, ...] = ("hi", "kn", "ta", "te", "bn")

# IndicTrans2 language tags (FLORES codes).
FLORES = {
    "en": "eng_Latn",
    "hi": "hin_Deva",
    "kn": "kan_Knda",
    "ta": "tam_Taml",
    "te": "tel_Telu",
    "bn": "ben_Beng",
}

MODEL_NAME = "ai4bharat/indictrans2-en-indic-dist-200M"
TIMEOUT_MS = 30_000


class Translator(Protocol):
    def translate(self, texts: list[str], target: str, source: str = "en") -> list[str]: ...


class FakeTranslator:
    """Deterministic stand-in: wraps the text in a target-language tag.

    Records every batch it receives so tests can assert batching and caching.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []

    def translate(self, texts: list[str], target: str, source: str = "en") -> list[str]:
        self.calls.append((list(texts), target))
        return [f"[{target}] {t}" for t in texts]


class IndicTrans2Translator:
    """Real model. Heavy imports and the model load happen once, in __init__."""

    def __init__(
        self, model_name: str = MODEL_NAME, device: str = "cpu", local_files_only: bool = False
    ) -> None:
        import torch
        from IndicTransToolkit.processor import IndicProcessor
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self._torch = torch
        self._device = device
        self._tokenizer = AutoTokenizer.from_pretrained(
            model_name, trust_remote_code=True, local_files_only=local_files_only
        )
        self._model = AutoModelForSeq2SeqLM.from_pretrained(
            model_name, trust_remote_code=True, local_files_only=local_files_only
        ).to(device)
        self._model.eval()
        self._processor = IndicProcessor(inference=True)

    def translate(self, texts: list[str], target: str, source: str = "en") -> list[str]:
        if not texts:
            return []
        src, tgt = FLORES[source], FLORES[target]
        batch = self._processor.preprocess_batch(texts, src_lang=src, tgt_lang=tgt)
        enc = self._tokenizer(batch, truncation=True, padding="longest", return_tensors="pt").to(
            self._device
        )
        with self._torch.inference_mode():
            out = self._model.generate(
                **enc, num_beams=5, num_return_sequences=1, max_length=256, use_cache=True
            )
        decoded = self._tokenizer.batch_decode(
            out, skip_special_tokens=True, clean_up_tokenization_spaces=True
        )
        return self._processor.postprocess_batch(decoded, lang=tgt)


LANG_NAMES = {"hi": "Hindi", "kn": "Kannada", "ta": "Tamil", "te": "Telugu", "bn": "Bengali"}
GEMINI_MODEL = "gemini-3.1-flash-lite"
# Flash-Lite ends Hindi lines with " |" and Bengali ones with "。" (bench, 27 Oct 2026).
_STRAY_STOP = re.compile(r"\s*[|\u3002\uff0e]\s*$")
log = logging.getLogger("ty.translate.gemini")


def normalise(text: str, target: str) -> str:
    """Danda (or a full stop) for a stray pipe or CJK stop the model left at the end."""
    stop = "।" if target in ("hi", "bn") else "."
    return _STRAY_STOP.sub(stop, text).replace("\u3002", stop)


class GeminiTranslator:
    """Gemini 3.1 Flash-Lite on Vertex AI, one call per batch. Logs every call (no text).

    Model from TY_MODEL_LITE; Vertex from GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_CLOUD_PROJECT and
    GOOGLE_CLOUD_LOCATION. `client` is injectable so tests never import or call the SDK.
    """

    def __init__(self, client: Any = None, model: str | None = None) -> None:
        self.model = model or os.environ.get("TY_MODEL_LITE", GEMINI_MODEL)
        if client is None:
            from google import genai
            from google.genai import types

            opts = types.HttpOptions(timeout=TIMEOUT_MS)
            if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true"):
                location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
                client = genai.Client(vertexai=True, location=location, http_options=opts)
            else:  # AI Studio (GEMINI_API_KEY); the SDK raises a clear error if neither is set
                client = genai.Client(http_options=opts)
        self._client = client

    def translate(self, texts: list[str], target: str, source: str = "en") -> list[str]:
        if not texts:
            return []
        prompt = (
            f"Translate each {LANG_NAMES.get(source, 'English')} string in this JSON array into "
            f"{LANG_NAMES[target]} for a traveller in India. Keep every token like XQ0Z and every "
            "[n] marker exactly as written, numbers and prices as they are, and the sentence "
            "punctuation of the target language. Return only a JSON array of "
            f"{len(texts)} strings in the same order.\n\n{json.dumps(texts, ensure_ascii=False)}"
        )
        t = time.perf_counter()
        r = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0},
        )
        usage = getattr(r, "usage_metadata", None)
        log.info(
            "gemini translate model=%s target=%s texts=%d seconds=%.2f tokens_in=%s tokens_out=%s",
            self.model,
            target,
            len(texts),
            time.perf_counter() - t,
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
        )
        out = json.loads(r.text)
        if (
            not isinstance(out, list)
            or len(out) != len(texts)
            or not all(isinstance(o, str) for o in out)
        ):
            raise ValueError(f"gemini returned {type(out).__name__} for {len(texts)} texts")
        # Lost XQnZ tokens and [n] markers are not checked here: TranslationService.restore flags a
        # lost entity, the clients drop a reply whose markers changed, and QA falls back to English.
        return [normalise(o, target) for o in out]
