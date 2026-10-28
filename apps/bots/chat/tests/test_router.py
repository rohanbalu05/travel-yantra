"""POST /chat end to end in-process: the router, SSE, the streaming ASGI transport, the store."""

import asyncio
import json
import os

import httpx
import pytest
from conftest import ITINERARY, done, sse
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from ty_chat import router
from ty_chat.models import Conversation
from ty_chat.store import MemoryStore, PgStore, set_store

DB = os.environ.get("DATABASE_URL")  # read before conftest clears it
CID = {"X-Client-Id": "browser-abcdef-0123456789"}


def app_with_fake_api(seen: list) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    @app.post("/plan")
    async def plan(request: Request):
        seen.append((dict(request.headers), await request.json()))

        async def events():
            yield sse({"stage": "planning", "message": "places", "step": "places"})
            await asyncio.sleep(0)
            yield sse(done())

        return StreamingResponse(events(), media_type="text/event-stream")

    return app


def frames(body: str) -> list[dict]:
    return [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:")]


@pytest.fixture(autouse=True)
def memory():
    store = MemoryStore()
    set_store(store)
    yield store
    set_store(None)


async def post(app, body: dict, headers=CID) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.post("/chat", json=body, headers=headers)


async def test_chat_streams_a_plan(memory):
    seen: list = []
    app = app_with_fake_api(seen)
    r = await post(app, {"text": "Plan Bengaluru to Goa, 11-14 Dec, 4 of us", "lang": "en"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    kinds = [f["type"] for f in frames(r.text)]
    assert kinds == ["note", "plan", "text", "chips", "done"]
    last = frames(r.text)[-1]
    assert last == {"type": "done", "plan_id": "p1", "share_token": "tok1",
                    "plan_changed": True, "lang": "en"}  # fmt: skip
    # The caller's id goes on to /plan, so the plan has the same owner as on the web.
    assert seen[0][0]["x-client-id"] == CID["X-Client-Id"]
    saved = await memory.get(CID["X-Client-Id"])
    assert saved.plan_id == "p1"
    assert saved.itinerary.request.destinations == ITINERARY["request"]["destinations"]


async def test_chat_needs_a_caller():
    r = await post(app_with_fake_api([]), {"text": "hi"}, headers={})
    assert r.status_code == 401


async def test_greeting_offers_chips():
    r = await post(app_with_fake_api([]), {"text": "namaste"})
    kinds = [f["type"] for f in frames(r.text)]
    assert kinds == ["text", "chips", "done"]


async def test_body_limits():
    r = await post(app_with_fake_api([]), {"text": "x" * 4001})
    assert r.status_code == 422


@pytest.mark.skipif(not DB, reason="DATABASE_URL is unset")
async def test_pg_store_round_trip():
    store = PgStore(DB)
    await store.put("test-chat-roundtrip-01", Conversation(draft=["Plan a trip to Goa"]))
    got = await store.get("test-chat-roundtrip-01")
    assert got.draft == ["Plan a trip to Goa"]
    await store.delete("test-chat-roundtrip-01")
    assert await store.get("test-chat-roundtrip-01") is None
