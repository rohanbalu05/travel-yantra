import json
import sys
import urllib.parse
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "packages" / "contracts" / "src"))


@pytest.fixture(autouse=True)
def isolated_api_cache(tmp_path, monkeypatch):
    """No test reads or writes the machine's shared API cache or call counter."""
    from routes import apicache, flights, hotels, roads

    monkeypatch.setenv("ROUTES_CACHE_FILE", str(tmp_path / "routes-cache.json"))
    for fn in (apicache.get_store, flights.default_flight_provider, hotels.default_hotel_provider,
               roads.default_road_provider):
        fn.cache_clear()
    yield
    for fn in (apicache.get_store, flights.default_flight_provider, hotels.default_hotel_provider,
               roads.default_road_provider):
        fn.cache_clear()


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class SerpFixtures:
    """SerpApi transport that answers from the recorded fixtures by request params
    and counts the calls. Unknown params raise, like a failed request."""

    def __init__(self) -> None:
        self.by_params: dict[str, dict] = {}
        for f in (FIXTURES / "serpapi").glob("*.json"):
            body = json.loads(f.read_text(encoding="utf-8"))
            params = {"currency": "INR", "gl": "in", "hl": "en", **body["_params"]}
            self.by_params[json.dumps(params, sort_keys=True)] = body
        self.calls: list[dict] = []

    def __call__(self, url: str, timeout: float) -> dict:
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        assert params.pop("api_key") == "test-key"
        self.calls.append(params)
        hit = self.by_params.get(json.dumps(params, sort_keys=True))
        if hit is None:
            raise TimeoutError("no fixture for these params")
        return hit


@pytest.fixture
def serp():
    """(SerpApi on a fresh memory store with a test key, its fixture transport)."""
    from routes.apicache import MemoryStore
    from routes.serpapi import SerpApi

    t = SerpFixtures()
    return SerpApi(store=MemoryStore(), transport=t, api_key="test-key"), t
