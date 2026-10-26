"""Batching and LRU caching around a Translator."""

from __future__ import annotations

from collections import OrderedDict
from threading import Lock

from .translator import Translator


class TranslationService:
    def __init__(self, translator: Translator, max_batch: int = 16, cache_size: int = 4096):
        if max_batch < 1:
            raise ValueError("max_batch must be >= 1")
        self._translator = translator
        self._max_batch = max_batch
        self._cache_size = cache_size
        self._cache: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._lock = Lock()

    def _get(self, key: tuple[str, str]) -> str | None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def _put(self, key: tuple[str, str], value: str) -> None:
        with self._lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

    def translate(self, texts: list[str], target: str, source: str = "en") -> list[str]:
        results: list[str | None] = [self._get((t, target)) for t in texts]
        # Unique misses, in first-seen order.
        missing = list(dict.fromkeys(t for t, r in zip(texts, results) if r is None))
        for i in range(0, len(missing), self._max_batch):
            chunk = missing[i : i + self._max_batch]
            for text, out in zip(chunk, self._translator.translate(chunk, target, source)):
                self._put((text, target), out)
        # Re-read from the cache; a miss here means the entry was evicted mid-call.
        final = dict(zip(missing, (self._get((t, target)) for t in missing)))
        return [r if r is not None else (final.get(t) or "") for t, r in zip(texts, results)]
