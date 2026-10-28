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
ACCOUNT_URL = "https://serpapi.com/account.json"  # free: not counted against the plan (serpapi.com/account-api)
ACCOUNT_TTL_S = 600  # the plan's remainder is read at most every 10 minutes (shared store)
RESERVE = 10  # live calls stop this many searches short of the plan's remainder (SERPAPI_RESERVE)
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
                 monthly_cap: int | None = None, account: bool | None = None) -> None:
        """account: check the plan's remainder (Account API) before each live call; default on
        for the real transport, off for test transports."""
        self.store = store if store is not None else apicache.get_store()
        self._transport = transport
        self._api_key = api_key
        self.daily_cap = daily_cap if daily_cap is not None else _cap("SERPAPI_DAILY_CAP", DAILY_CAP)
        self.monthly_cap = monthly_cap if monthly_cap is not None else _cap("SERPAPI_MONTHLY_CAP", MONTHLY_CAP)
        self.live_calls = 0  # this instance only; the shared count is in the store
        self.account = account if account is not None else transport is urllib_transport
        self.reserve = _cap("SERPAPI_RESERVE", RESERVE)

    def _key(self) -> str | None:
        return self._api_key or os.environ.get("SERPAPI_API_KEY")

    def get(self, params: dict, ttl_s: int) -> dict | None:
        params = {"currency": "INR", "gl": "in", "hl": "en", **params}
        ck = cache_key(params)
        if (hit := self.store.get(ck)) is not None:
            return hit
        key = self._key()
        if key and self.store.get(ck + ":error") is None and self._plan_allows(key) and self._spend():
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

    def searches_left(self, key: str) -> int | None:
        """The plan's searches left (Account API, cached ACCOUNT_TTL_S, less the live calls made since);
        None when unknown. Only the number is kept: the account answer also holds the key and email."""
        hit = self.store.get("serpapi:account")
        if hit is None:
            try:
                d = self._transport(f"{ACCOUNT_URL}?{urllib.parse.urlencode({'api_key': key})}", TIMEOUT_S)
                left = d.get("total_searches_left") if isinstance(d, dict) else None
            except Exception as exc:  # unknown: the caps still apply
                log.warning("serpapi account check failed (%s)", type(exc).__name__)
                return None
            if not isinstance(left, int):
                return None
            hit = {"left": left, "calls": self.store.count(PROVIDER, apicache.month_period())}
            self.store.set("serpapi:account", hit, ACCOUNT_TTL_S)
        return hit["left"] - (self.store.count(PROVIDER, apicache.month_period()) - hit["calls"])

    def _plan_allows(self, key: str) -> bool:
        if not self.account:
            return True
        left = self.searches_left(key)
        if left is not None and left <= self.reserve:
            log.warning("serpapi plan has %d searches left; keeping the last %d", left, self.reserve)
            return False
        return True

    def _spend(self) -> bool:
        # Daily first: once the day is used up no monthly slot is touched; a refused
        # monthly spend costs one unused daily slot at worst.
        return (self.store.spend(PROVIDER, apicache.day_period(), self.daily_cap)
                and self.store.spend(PROVIDER, apicache.month_period(), self.monthly_cap))
