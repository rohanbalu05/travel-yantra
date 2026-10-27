"""SerpApi client for Google Flights and Google Hotels: every response cached in
the shared store, every live call counted against a daily and a monthly cap
shared by all instances (SerpApi free plan). The key comes from the env var
SERPAPI_API_KEY and is never cached, logged or written to a fixture.

`get` returns the cached payload when fresh; otherwise one live call if the key
is set and both caps allow it; otherwise the stale cached payload, if any;
otherwise None, and the caller falls back to its offline data. A failed call
is remembered for ERROR_TTL_S and not repeated meanwhile."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.parse
import urllib.request
from collections.abc import Callable

from . import apicache

URL = "https://serpapi.com/search.json"
TIMEOUT_S = 20.0  # booking options can take over 12 s
PROVIDER = "serpapi"
DAILY_CAP = 20
MONTHLY_CAP = 100
ERROR_TTL_S = 600  # a failed request is not retried for 10 minutes, so errors cannot drain the cap
# Response parts we never keep: request metadata (ids, endpoint links) and phone numbers.
DROP_KEYS = frozenset({"search_metadata", "serpapi_pagination", "pagination", "phone", "phone_link",
                       "api_key", "raw_html_file", "json_endpoint"})

log = logging.getLogger(__name__)

#: (url with query, timeout) -> parsed JSON.
Transport = Callable[[str, float], dict]


def urllib_transport(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def sanitise(payload, secret: str | None = None):
    """Drop request metadata and phone fields, recursively; blank any string that
    contains the key (belt and braces: SerpApi does not echo it)."""
    if isinstance(payload, dict):
        return {k: sanitise(v, secret) for k, v in payload.items() if k not in DROP_KEYS}
    if isinstance(payload, list):
        return [sanitise(v, secret) for v in payload]
    if isinstance(payload, str) and secret and secret in payload:
        return ""
    return payload


def cache_key(params: dict) -> str:
    return "serpapi:" + hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()


def _cap(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class SerpApi:
    def __init__(self, store: apicache.Store | None = None, transport: Transport = urllib_transport,
                 api_key: str | None = None, daily_cap: int | None = None,
                 monthly_cap: int | None = None) -> None:
        self.store = store if store is not None else apicache.get_store()
        self._transport = transport
        self._api_key = api_key
        self.daily_cap = daily_cap if daily_cap is not None else _cap("SERPAPI_DAILY_CAP", DAILY_CAP)
        self.monthly_cap = monthly_cap if monthly_cap is not None else _cap("SERPAPI_MONTHLY_CAP", MONTHLY_CAP)
        self.live_calls = 0  # this instance only; the shared count is in the store

    def _key(self) -> str | None:
        return self._api_key or os.environ.get("SERPAPI_API_KEY")

    def get(self, params: dict, ttl_s: int) -> dict | None:
        params = {"currency": "INR", "gl": "in", "hl": "en", **params}
        ck = cache_key(params)
        if (hit := self.store.get(ck)) is not None:
            return hit
        key = self._key()
        if key and self.store.get(ck + ":error") is None and self._spend():
            self.live_calls += 1
            url = f"{URL}?{urllib.parse.urlencode({**params, 'api_key': key})}"
            try:
                payload = self._transport(url, TIMEOUT_S)
            except Exception as exc:  # network, HTTP or JSON error: never fail the request
                log.warning("serpapi %s call failed (%s)", params.get("engine"), type(exc).__name__)
                payload = None
            if isinstance(payload, dict) and not payload.get("error"):
                clean = sanitise(payload, key)
                self.store.set(ck, clean, ttl_s)
                log.info("serpapi live call (%s), %d today", params.get("engine"),
                         self.store.count(PROVIDER, apicache.day_period()))
                return clean
            if isinstance(payload, dict):
                log.warning("serpapi %s returned an error", params.get("engine"))
            self.store.set(ck + ":error", {"error": True}, ERROR_TTL_S)
        return self.store.get(ck, stale=True)

    def _spend(self) -> bool:
        # Daily first: once the day is used up no monthly slot is touched; a refused
        # monthly spend costs one unused daily slot at worst.
        return (self.store.spend(PROVIDER, apicache.day_period(), self.daily_cap)
                and self.store.spend(PROVIDER, apicache.month_period(), self.monthly_cap))
