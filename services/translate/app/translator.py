"""Translator interface, a deterministic fake, and the IndicTrans2 implementation."""

from __future__ import annotations

from typing import Literal, Protocol

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

    def __init__(self, model_name: str = MODEL_NAME, device: str = "cpu") -> None:
        import torch
        from IndicTransToolkit.processor import IndicProcessor
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self._torch = torch
        self._device = device
        self._tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(
            model_name, trust_remote_code=True
        ).to(device)
        self._model.eval()
        self._processor = IndicProcessor(inference=True)

    def translate(self, texts: list[str], target: str, source: str = "en") -> list[str]:
        if not texts:
            return []
        src, tgt = FLORES[source], FLORES[target]
        batch = self._processor.preprocess_batch(texts, src_lang=src, tgt_lang=tgt)
        enc = self._tokenizer(
            batch, truncation=True, padding="longest", return_tensors="pt"
        ).to(self._device)
        with self._torch.inference_mode():
            out = self._model.generate(
                **enc, num_beams=5, num_return_sequences=1, max_length=256, use_cache=True
            )
        decoded = self._tokenizer.batch_decode(
            out, skip_special_tokens=True, clean_up_tokenization_spaces=True
        )
        return self._processor.postprocess_batch(decoded, lang=tgt)
