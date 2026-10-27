import logging
import threading
from types import ModuleType

from fastapi.testclient import TestClient

import main


def lane(name: str, warm=None) -> ModuleType:
    mod = ModuleType(name)
    if warm:
        mod.warm_up = warm
    return mod


def test_health_answers_while_a_slow_warm_up_is_still_running(monkeypatch):
    release, done = threading.Event(), threading.Event()

    def slow():
        release.wait(5)
        done.set()

    monkeypatch.setenv("TY_WARM_UP", "1")
    monkeypatch.setattr(main, "MOUNTED", [lane("slowlane", slow), lane("nolane")])
    with TestClient(main.app) as client:  # entering the context runs the lifespan
        assert client.get("/health").status_code == 200
        assert not done.is_set()  # still warming
        release.set()
        assert done.wait(5)


def test_a_failing_warm_up_is_logged_and_ignored(monkeypatch, caplog):
    def boom():
        raise RuntimeError("no model")

    threads = main.warm_up([lane("badlane", boom)])
    with caplog.at_level(logging.ERROR, logger="main"):
        for t in threads:
            t.join(5)
    assert any("warm_up badlane failed" in r.getMessage() for r in caplog.records)


def test_warm_up_can_be_turned_off(monkeypatch):
    called = threading.Event()
    monkeypatch.setattr(main, "MOUNTED", [lane("lane", called.set)])
    monkeypatch.setenv("TY_WARM_UP", "0")
    with TestClient(main.app) as client:
        client.get("/health")
    assert not called.is_set()


def test_lanes_without_warm_up_start_no_thread():
    assert main.warm_up([lane("plain")]) == []
