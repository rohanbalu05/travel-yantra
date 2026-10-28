import json

import httpx
import pytest
from ty_contracts import Lang

from ty_chat.api import SAMPLE, Api
from ty_chat.engine import Engine
from ty_chat.lite import Edit
from ty_chat.models import ChatIn
from ty_chat.store import MemoryStore

ITINERARY = json.loads(SAMPLE.read_text(encoding="utf-8"))["itinerary"]
CID = "test-client-0001"


@pytest.fixture(autouse=True)
def _no_live_services(monkeypatch):
    # Tests never reach a real API, translate service or model, whatever the shell has set.
    for name in ("TRANSLATE_URL", "K_SERVICE", "SHARE_BASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TY_FAKE_LLM", "1")


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


class FakeLite:
    """Counts calls; returns the Edit or words it was given."""

    def __init__(self, edit: Edit | None = None, words: str = "") -> None:
        self.next_edit, self.words = edit or Edit(), words
        self.edits: list[str] = []
        self.heard: list[tuple[bytes, str]] = []

    async def edit(self, plan: str, text: str) -> Edit:
        self.edits.append(text)
        return self.next_edit

    async def transcribe(self, audio: bytes, mime: str) -> str:
        self.heard.append((audio, mime))
        return self.words


def sse(*events: dict) -> str:
    return "".join(f": ping\n\ndata: {json.dumps(e)}\n\n" for e in events)


def done(itinerary=ITINERARY, plan_id="p1", token="tok1") -> dict:
    return {
        "stage": "done",
        "message": "done",
        "partial": itinerary,
        "plan_id": plan_id,
        "share_token": token,
    }


def asks(*questions: str, draft: dict | None = None) -> dict:
    return {
        "stage": "needs_input",
        "message": "need more",
        "questions": list(questions),
        "draft": draft,
    }


class FakeApi:
    """Records requests; `plans` are the /plan streams to return, in order."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.plans: list[str] = []
        self.revisions: list[str] = []
        self.guide = {"text": "The guide's answer.", "citations": []}

    def bodies(self, path: str) -> list[dict]:
        return [json.loads(r.content) for r in self.requests if r.url.path == path]

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        path = req.url.path
        if path == "/plan":
            return httpx.Response(200, text=self.plans.pop(0))
        if path.endswith("/revise"):
            return httpx.Response(200, text=self.revisions.pop(0))
        if path == "/guide/ask":
            return httpx.Response(200, json=self.guide)
        return httpx.Response(404, json={"detail": "Not Found"})


@pytest.fixture
def api():
    return FakeApi()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def lite():
    return FakeLite()


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def engine(api, store, clock, lite):
    transport = httpx.MockTransport(api.handler)
    return Engine(Api("http://api", transport, {"X-Client-Id": CID}), store, lite=lite, clock=clock)


async def send(engine: Engine, text: str = "", cid: str = CID, **kw) -> list:
    return [e async for e in engine.chat(cid, ChatIn(text=text, **kw))]


def texts(events) -> list[str]:
    return [e.text for e in events if e.type == "text"]


def of(events, kind: str) -> list:
    return [e for e in events if e.type == kind]


__all__ = ["Lang"]
