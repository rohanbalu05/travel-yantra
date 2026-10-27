import asyncio
import logging
from types import SimpleNamespace

import pytest
from google.genai import errors, types

from core import llm


def err(code: int) -> errors.APIError:
    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, {"error": {"code": code, "message": "sample", "status": "X"}})


class FakeClient:
    """Stands in for genai.Client: raises the queued errors, then answers."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self.generate_content))

    async def generate_content(self, model, contents, config):
        self.calls.append(config.http_options.timeout)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return SimpleNamespace(text=out)


def clock(*ticks):
    """A fake monotonic clock: returns the ticks in order, then keeps returning the last one."""
    seq = list(ticks)
    return lambda: seq.pop(0) if len(seq) > 1 else seq[0]


@pytest.fixture
def model(monkeypatch):
    slept = []

    async def no_sleep(s):
        slept.append(s)

    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(llm.random, "uniform", lambda a, b: b)  # worst-case jitter
    m = object.__new__(llm.GeminiModel)  # no real client, no network
    m._types = types
    m.slept = slept
    return m


def test_retries_429_and_503_then_answers(model, caplog):
    model._client = FakeClient([err(429), err(503), "ok"])
    with caplog.at_level(logging.WARNING, logger="core.llm"):
        assert asyncio.run(model.text("hi")) == "ok"
    assert len(model._client.calls) == 3 and model.slept == [1.0, 2.0]
    assert [r.message.split(";")[0] for r in caplog.records] == [
        "model gemini-3.5-flash returned 429", "model gemini-3.5-flash returned 503"]


def test_gives_up_after_three_tries(model):
    model._client = FakeClient([err(429), err(429), err(429), "never"])
    with pytest.raises(errors.ClientError):
        asyncio.run(model.text("hi"))
    assert len(model._client.calls) == 3


def test_other_errors_are_not_retried(model):
    model._client = FakeClient([err(400), "never"])
    with pytest.raises(errors.ClientError):
        asyncio.run(model.text("hi"))
    assert len(model._client.calls) == 1 and model.slept == []


def test_each_try_gets_only_the_time_left_in_the_budget(model, monkeypatch):
    monkeypatch.setattr(llm, "_now", clock(0.0, 0.0, 15.0))
    model._client = FakeClient([err(503), "ok"])
    assert asyncio.run(model.text("hi")) == "ok"
    first, second = model._client.calls
    assert first == 20_000 and second == 5_000


def test_no_retry_when_the_budget_is_spent(model, monkeypatch):
    monkeypatch.setattr(llm, "_now", clock(0.0, 0.0, 19.5))
    model._client = FakeClient([err(429), "never"])
    with pytest.raises(errors.ClientError):
        asyncio.run(model.json("hi", llm.BaseModel))
    assert len(model._client.calls) == 1


def test_timeout_s_replaces_the_default_budget(model, monkeypatch):
    monkeypatch.setattr(llm, "_now", clock(0.0, 0.0, 30.0))
    model._client = FakeClient([err(503), "ok"])
    assert asyncio.run(model.text("long story", timeout_s=60)) == "ok"
    assert model._client.calls == [60_000, 30_000]
