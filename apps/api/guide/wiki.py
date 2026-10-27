"""Wikimedia fetchers (card #21): Wikipedia and Wikivoyage text, Wikidata labels.

Free APIs, used politely: a descriptive User-Agent, timeouts, and every response
cached (Postgres `places_cache`, which is a plain key/payload table, or in
memory for tests). Text is CC BY-SA; every chunk built from it keeps its page URL
as the source.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode

from .places import Cache, MemoryCache, Transport, urllib_transport

USER_AGENT = "TravelYantra/0.1 (https://github.com/rohanbalu05/travel-yantra; guide lane)"
TIMEOUT_S = 10.0
TTL_S = 30 * 24 * 3600
LANGS = ("en", "hi", "kn", "ta", "te", "bn")
#: Sections that are lists of links or references, not prose about the place.
SKIP_SECTIONS = re.compile(r"^(see also|references|notes|external links|further reading|gallery|"
                           r"bibliography|sources|citations|go next|connect|stay safe|cope)$", re.I)  # fmt: skip


class WikiClient:
    def __init__(self, cache: Cache | None = None, transport: Transport = urllib_transport):
        self.cache = cache or MemoryCache()
        self._transport = transport
        self.calls = 0  # live requests made (cache misses), for the call log

    def _get(self, url: str) -> dict:
        key = "wiki:" + hashlib.sha256(url.encode()).hexdigest()
        if (hit := self.cache.get(key)) is not None:
            return hit
        self.calls += 1
        payload = self._transport("GET", url, {"User-Agent": USER_AGENT, "Accept": "application/json"},
                                  None, TIMEOUT_S)  # fmt: skip
        self.cache.set(key, payload, TTL_S)
        return payload

    def summary(self, title: str, lang: str = "en") -> dict:
        """REST summary: title, extract (the lead paragraph), page URL, coordinates."""
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"
        try:
            raw = self._get(url)
        except HTTPError as e:
            if e.code != 404:
                raise
            raw = {}  # no such page: the caller skips it
        return {
            "title": raw.get("title", title),
            "extract": raw.get("extract", ""),
            "url": (raw.get("content_urls") or {}).get("desktop", {}).get("page"),
            "lat": (raw.get("coordinates") or {}).get("lat"),
            "lng": (raw.get("coordinates") or {}).get("lon"),
        }

    def sections(self, title: str, site: str = "wikipedia") -> tuple[str, list[tuple[str, str]]]:
        """(page URL, [(section heading, plain text)]) for a whole article, lead first."""
        params = {"action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1,
                  "exsectionformat": "wiki", "titles": title, "format": "json", "formatversion": 2}  # fmt: skip
        raw = self._get(f"https://en.{site}.org/w/api.php?{urlencode(params)}")
        pages = raw.get("query", {}).get("pages") or [{}]
        page = pages[0]
        text = page.get("extract") or ""
        url = f"https://en.{site}.org/wiki/{quote(page.get('title', title).replace(' ', '_'))}"
        # re.split with two groups gives [lead, "==", heading, body, "==", heading, body, ...]
        parts = re.split(r"^(={2,})\s*(.+?)\s*\1\s*$", text, flags=re.M)
        found = [("Introduction", parts[0])] + [
            (parts[i + 1], parts[i + 2]) for i in range(1, len(parts) - 2, 3)
        ]
        return url, [(h, b.strip()) for h, b in found if b.strip() and not SKIP_SECTIONS.match(h)]

    def labels(self, title: str) -> dict[str, Any]:
        """Wikidata for an English Wikipedia title: qid, labels in our six languages, coordinates."""
        params = {"action": "wbgetentities", "sites": "enwiki", "titles": title, "props": "labels|claims",
                  "languages": "|".join(LANGS), "format": "json", "redirects": "yes"}  # fmt: skip
        raw = self._get(f"https://www.wikidata.org/w/api.php?{urlencode(params)}")
        entity = next((e for e in raw.get("entities", {}).values() if "missing" not in e), None)
        if not entity:
            return {"qid": None, "labels": {}, "lat": None, "lng": None}
        coord = next(iter(entity.get("claims", {}).get("P625", [])), None)
        value = (((coord or {}).get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
        return {
            "qid": entity.get("id"),
            "labels": {lang: v["value"] for lang, v in entity.get("labels", {}).items() if lang in LANGS},
            "lat": value.get("latitude"),
            "lng": value.get("longitude"),
        }


def paragraphs(text: str, *, min_words: int = 25, max_words: int = 160) -> list[str]:
    """Prose paragraphs a story can stand on: not headings, not one-liners, not walls."""
    out = []
    for para in re.split(r"\n\s*\n|\n", text):
        para = " ".join(para.split())
        n = len(para.split())
        if n < min_words:
            continue
        if n > max_words:  # cut on a sentence boundary
            sentences, kept = re.split(r"(?<=[.!?])\s+", para), []
            for s in sentences:
                if len(" ".join(kept + [s]).split()) > max_words:
                    break
                kept.append(s)
            para = " ".join(kept) or " ".join(para.split()[:max_words])
        out.append(para)
    return out


def dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)
