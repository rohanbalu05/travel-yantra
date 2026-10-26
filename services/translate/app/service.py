"""Batching and LRU caching around a Translator."""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock

from . import checks, phrasebook
from .translator import Translator

_PLACEHOLDER = re.compile(r"XQ\d+Z")


@dataclass
class Result:
    text: str
    via: str  # "phrasebook" or "model"
    flags: list[str] = field(default_factory=list)


class TranslationService:
    def __init__(
        self,
        translator: Translator,
        max_batch: int = 16,
        cache_size: int = 4096,
        entity_names: dict[str, dict[str, str]] | None = None,
        book: dict[str, dict[str, str]] | None = None,
    ):
        if max_batch < 1:
            raise ValueError("max_batch must be >= 1")
        if cache_size < 0:
            raise ValueError("cache_size must be >= 0")
        self._translator = translator
        self._max_batch = max_batch
        self._cache_size = cache_size
        self._cache: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._lock = Lock()
        self._names = entity_names or {}
        self._book = phrasebook.load() if book is None else book

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
        local: dict[str, str] = {}
        for t in texts:
            hit = self._get((t, target))
            if hit is not None:
                local[t] = hit
        # Unique misses, in first-seen order.
        missing = list(dict.fromkeys(t for t in texts if t not in local))
        for i in range(0, len(missing), self._max_batch):
            chunk = missing[i : i + self._max_batch]
            for text, out in zip(chunk, self._translator.translate(chunk, target, source)):
                local[text] = out  # request-local, so LRU eviction cannot lose it
                self._put((text, target), out)
        return [local[t] for t in texts]

    def translate_checked(
        self, texts: list[str], target: str, source: str = "en", entities: list[str] | None = None
    ) -> list[Result]:
        """Phrasebook first (no model), then the model with entity names protected, then checks."""
        entities = entities or []
        results: list[Result | None] = [None] * len(texts)
        todo: list[tuple[int, str, dict[str, str]]] = []
        for i, t in enumerate(texts):
            hit = phrasebook.lookup(t, target, self._book)
            if hit is not None:
                results[i] = Result(hit, "phrasebook", checks.check(t, hit, target))
            else:
                prepared, slots = checks.protect(t, entities)
                todo.append((i, prepared, slots))
        outs = self.translate([p for _, p, _ in todo], target, source)
        for (i, _, slots), out in zip(todo, outs):
            final, lost = checks.restore(out, slots, self._names, target)
            flags = checks.check(texts[i], final, target, _PLACEHOLDER.sub("", out))
            results[i] = Result(final, "model", flags + lost)
        return results  # type: ignore[return-value]
