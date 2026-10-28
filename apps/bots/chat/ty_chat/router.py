"""POST /chat, mounted on ty-api by TY1 (main.py LANES). Streams ChatEvents as Server-Sent Events.

The caller is the signed-in account or the browser's X-Client-Id (core.accounts.client_id), and
the WhatsApp bot's per-sender id. The engine calls the API in-process with the caller's headers,
so plans belong to the same owner as on the web.
"""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from .api import Api, AsgiStream
from .engine import Engine
from .models import ChatIn

PING_SECONDS = 15.0  # Cloud Run drops idle streams
CLIENT_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
FORWARD = ("x-client-id", "authorization")

try:  # inside ty-api: the same identity as /plan (account, else X-Client-Id)
    from core.accounts import client_id as _caller
except ImportError:  # this package's own tests and local runs: X-Client-Id only

    def _caller(x_client_id: str | None = Header(default=None)) -> str | None:
        return x_client_id if x_client_id and CLIENT_ID.match(x_client_id) else None


router = APIRouter()


async def sse(events, ping: float = PING_SECONDS):
    """`data: <ChatEvent JSON>` frames with `: ping` comments while a slow step runs."""
    it = aiter(events)
    pending = asyncio.ensure_future(anext(it))
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=ping)
            if not done:
                yield ": ping\n\n"
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            yield f"data: {event.model_dump_json(exclude_none=True, by_alias=True)}\n\n"
            pending = asyncio.ensure_future(anext(it))
    finally:
        pending.cancel()


def engine_for(request: Request) -> Engine:
    headers = {k: v for k in FORWARD if (v := request.headers.get(k))}
    return Engine(Api("http://api", AsgiStream(request.app), headers))


@router.post("/chat")
async def chat(body: ChatIn, request: Request, caller: str | None = Depends(_caller)):
    """One chat message (text, a voice note or a location) -> reply events: heard, note, text,
    chips, plan (with the itinerary), audio, then done (plan id, plan_changed, language)."""
    if caller is None:
        raise HTTPException(401, "sign in, or send X-Client-Id: 16-128 characters of A-Z, a-z, 0-9, _ or -")
    events = engine_for(request).chat(caller, body)
    return StreamingResponse(
        sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
