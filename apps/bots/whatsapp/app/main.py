"""WhatsApp Cloud API webhook: GET /webhook (verify), POST /webhook (messages), GET /health."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from collections import OrderedDict

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from .brain import Brain
from .sender import CloudApiSender, Sender

log = logging.getLogger(__name__)
SORRY = "Sorry, something went wrong on our side. Please try again in a minute."


def signature_ok(body: bytes, header: str | None, secret: str) -> bool:
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def incoming(payload: dict) -> list[dict]:
    """Messages from a webhook payload; status updates (sent, delivered, read) are skipped."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            out.extend(change.get("value", {}).get("messages", []))
    return out


class Seen:
    """Message ids already handled; Meta retries a webhook until it gets a 200."""

    def __init__(self, size: int = 1000) -> None:
        self.ids: OrderedDict[str, None] = OrderedDict()
        self.size = size

    def add(self, msg_id: str) -> bool:
        if msg_id in self.ids:
            return False
        self.ids[msg_id] = None
        if len(self.ids) > self.size:
            self.ids.popitem(last=False)
        return True


def create_app(brain: Brain | None = None, sender: Sender | None = None) -> FastAPI:
    app = FastAPI(title="Travel Yantra WhatsApp bot")
    brain = brain or Brain()
    sender = sender or CloudApiSender()
    seen = Seen()

    async def handle(msg: dict) -> None:
        try:
            reply = await brain.handle(msg)
        except Exception:
            log.exception("reply failed for a %s message", msg.get("type"))
            reply = SORRY
        await sender.send_text(msg.get("from", ""), reply)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/webhook", response_class=PlainTextResponse)
    def verify(
        mode: str = Query("", alias="hub.mode"),
        token: str = Query("", alias="hub.verify_token"),
        challenge: str = Query("", alias="hub.challenge"),
    ) -> str:
        expected = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
        if mode == "subscribe" and expected and hmac.compare_digest(token, expected):
            return challenge
        raise HTTPException(403, "verification failed")

    @app.post("/webhook")
    async def receive(request: Request, tasks: BackgroundTasks) -> dict:
        body = await request.body()
        secret = os.environ.get("WHATSAPP_APP_SECRET", "")
        if not signature_ok(body, request.headers.get("x-hub-signature-256"), secret):
            raise HTTPException(401, "bad signature")
        try:
            payload = json.loads(body)
        except ValueError as e:
            raise HTTPException(400, "body is not JSON") from e
        # Answer Meta at once; replies (which may take a while to plan) go out after.
        for msg in incoming(payload):
            if not msg.get("id") or seen.add(msg["id"]):
                tasks.add_task(handle, msg)
        return {"ok": True}

    return app


app = create_app()
