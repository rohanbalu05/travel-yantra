import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.service import TranslationService
from app.translator import FakeTranslator


def make(max_batch=2, cache_size=100):
    fake = FakeTranslator()
    return fake, TranslationService(fake, max_batch=max_batch, cache_size=cache_size)


def test_batching_splits_into_chunks():
    fake, svc = make(max_batch=2)
    out = svc.translate(["a", "b", "c", "d", "e"], "hi")
    assert [len(c[0]) for c in fake.calls] == [2, 2, 1]
    assert out == [f"[hi] {x}" for x in "abcde"]


def test_second_call_hits_cache():
    fake, svc = make()
    first = svc.translate(["hello", "world"], "kn")
    n = len(fake.calls)
    assert svc.translate(["hello", "world"], "kn") == first
    assert len(fake.calls) == n


def test_cache_keyed_on_target_and_dedupes():
    fake, svc = make(max_batch=10)
    svc.translate(["x", "x"], "hi")
    assert fake.calls == [(["x"], "hi")]
    svc.translate(["x"], "ta")
    assert len(fake.calls) == 2


def test_lru_evicts_oldest():
    fake, svc = make(max_batch=10, cache_size=1)
    svc.translate(["a"], "hi")
    svc.translate(["b"], "hi")
    svc.translate(["a"], "hi")
    assert len(fake.calls) == 3


def test_api_ok_health_and_422():
    with TestClient(create_app()) as c:
        assert c.get("/health").json() == {"status": "ok"}
        r = c.post("/translate", json={"texts": ["hi"], "target": "ta"})
        assert r.status_code == 200
        assert r.json()["translations"] == ["[ta] hi"]
        assert c.post("/translate", json={"texts": ["hi"], "target": "xx"}).status_code == 422
        assert c.post("/translate", json={"texts": ["hi"], "target": "en"}).status_code == 422
