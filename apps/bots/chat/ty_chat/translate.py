"""Reply translation through services/translate (TRANSLATE_URL); English when it can't help."""

from __future__ import annotations

import logging
import os
import re
import time

import httpx
from ty_contracts import Lang

log = logging.getLogger(__name__)
MARKER = re.compile(r"\[\d+\]")  # guide citation markers, kept as they are
SENTENCE = re.compile(r"(?<=[.!?।])\s+")
MAX_TEXT = 1000  # per-text cap of POST /translate
MAX_ENTITIES = 50
MAX_TEXTS = 200  # per-request cap of POST /translate
METADATA_TOKEN = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
)
TOKEN_SECONDS = 50 * 60  # Google ID tokens last an hour


def sentences(line: str) -> list[str]:
    """Split a long line so each piece fits the translate service's per-text cap."""
    return SENTENCE.split(line) if len(line) > MAX_TEXT else [line]


class Translator:
    def __init__(self, base: str | None = None) -> None:
        base = base if base is not None else os.environ.get("TRANSLATE_URL", "")
        self.base = base.rstrip("/")
        self._token: tuple[str, float] | None = None  # (ID token, expiry on the monotonic clock)

    async def _auth(self, client: httpx.AsyncClient) -> dict[str, str]:
        """ty-translate is private on Cloud Run: send an ID token for it from the metadata server.

        Only on Cloud Run (K_SERVICE set) with an https TRANSLATE_URL; local runs send nothing.
        """
        if not (os.environ.get("K_SERVICE") and self.base.startswith("https://")):
            return {}
        if self._token is None or time.monotonic() > self._token[1]:
            r = await client.get(
                METADATA_TOKEN,
                params={"audience": self.base},
                headers={"Metadata-Flavor": "Google"},
            )
            r.raise_for_status()
            self._token = (r.text.strip(), time.monotonic() + TOKEN_SECONDS)
        return {"Authorization": f"Bearer {self._token[0]}"}

    async def texts(self, texts: list[str], lang: Lang, keep: list[str] = ()) -> list[str]:
        """Translate each text to `lang`. `keep` (place names) and [n] markers are not translated.

        A text the service flags (wrong script, length, lost name) stays English.
        """
        if lang == Lang.en or not self.base:
            return texts
        # Empty texts need nothing; a single sentence over the cap stays English, never cut.
        todo = [i for i, t in enumerate(texts) if t.strip() and len(t) <= MAX_TEXT]
        if not todo:
            return texts
        out = list(texts)
        async with httpx.AsyncClient(timeout=60) as client:
            for b in range(0, len(todo), MAX_TEXTS):
                batch = todo[b : b + MAX_TEXTS]
                markers = {m for i in batch for m in MARKER.findall(texts[i])}
                entities = sorted(markers) + [k for k in dict.fromkeys(keep) if k]
                body = {
                    "texts": [texts[i] for i in batch],
                    "target": lang.value,
                    "entities": entities[:MAX_ENTITIES],
                }
                try:
                    headers = await self._auth(client)
                    r = await client.post(f"{self.base}/translate", json=body, headers=headers)
                    r.raise_for_status()
                    data = r.json()
                    pairs = list(zip(data["translations"], data["flags"], strict=True))
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    log.exception("translate failed; this part stays English")
                    continue
                for i, (text, flags) in zip(batch, pairs):
                    if not flags and MARKER.findall(text) == MARKER.findall(texts[i]):
                        out[i] = text
        return out

    async def text(self, text: str, lang: Lang, keep: list[str] = ()) -> str:
        """Translate a multi-line reply line by line (long lines by sentence)."""
        if lang == Lang.en or not self.base:
            return text
        lines = [sentences(line) for line in text.split("\n")]
        outs = iter(await self.texts([p for line in lines for p in line], lang, keep))
        return "\n".join(" ".join(next(outs) for _ in line) for line in lines)
