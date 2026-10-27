"""WhatsApp Cloud API webhook: GET /webhook (verify), POST /webhook (messages), GET /health."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from collections import OrderedDict

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from .brain import MAX_REPLY, Brain
from .sender import CloudApiSender, Sender

log = logging.getLogger(__name__)
SORRY = "Sorry, something went wrong on our side. Please try again in a minute."


def signature_ok(body: bytes, header: str | None, secret: str) -> bool:
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def _values(payload: dict) -> list[dict]:
    return [
        change.get("value", {})
        for entry in payload.get("entry", [])
        for change in entry.get("changes", [])
    ]


def incoming(payload: dict) -> list[dict]:
    """Messages from a webhook payload; status updates (sent, delivered, read) are skipped."""
    return [m for v in _values(payload) for m in v.get("messages", [])]


def failed_statuses(payload: dict) -> list[str]:
    """'failed' delivery reports for our replies, as 'code title' (Meta's reason, no number)."""
    out = []
    for v in _values(payload):
        for s in v.get("statuses", []):
            if s.get("status") == "failed":
                out += [
                    f"{e.get('code')} {e.get('title', '')}".strip() for e in s.get("errors", [])
                ]
    return out


def split(text: str, limit: int = MAX_REPLY) -> list[str]:
    """WhatsApp-sized parts: break at a blank line, else a line, else a space; never mid-word
    unless one word is longer than a message."""
    text, parts = text.strip(), []
    while len(text) > limit:
        for sep in ("\n\n", "\n", " "):
            cut = text.rfind(sep, 0, limit + 1)
            if cut > 0:
                break
        else:
            cut = limit
        if part := text[:cut].rstrip():
            parts.append(part)
        text = text[cut:].lstrip()
    return [*parts, text] if text or not parts else parts


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
        to = msg.get("from", "")

        async def notify(text: str) -> None:
            await sender.send_text(to, text)

        audio: list[str] = []
        try:
            reply = await brain.handle(msg, notify=notify, audio=audio)
        except Exception:
            log.exception("reply failed for a %s message", msg.get("type"))
            reply, audio = SORRY, []
        for part in split(reply):
            await sender.send_text(to, part)
        for url in audio:  # Katha chapters, in order, after their text
            await sender.send_audio(to, url)

    @app.get("/health")
    def health() -> dict:
        # GIT_SHA is set by the deploy (infra/gcp/run-services.sh, deploy.yml), as for ty-api.
        return {"ok": True, "version": os.environ.get("GIT_SHA") or "dev"}

    @app.get("/webhook", response_class=PlainTextResponse)
    def verify(
        mode: str = Query("", alias="hub.mode"),
        token: str = Query("", alias="hub.verify_token"),
        challenge: str = Query("", alias="hub.challenge"),
    ) -> str:
        expected = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
        if mode == "subscribe" and expected and hmac.compare_digest(token, expected):
            log.info("webhook verified")
            return challenge
        log.warning("webhook verification refused (mode %r)", mode)
        raise HTTPException(403, "verification failed")

    @app.post("/webhook")
    async def receive(request: Request) -> dict:
        body = await request.body()
        secret = os.environ.get("WHATSAPP_APP_SECRET", "")
        if not signature_ok(body, request.headers.get("x-hub-signature-256"), secret):
            log.warning(
                "POST /webhook refused: bad signature (header %s, app secret %s)",
                "present" if request.headers.get("x-hub-signature-256") else "missing",
                "set" if secret else "UNSET",
            )
            raise HTTPException(401, "bad signature")
        try:
            payload = json.loads(body)
        except ValueError as e:
            raise HTTPException(400, "body is not JSON") from e
        msgs = incoming(payload)
        for reason in failed_statuses(payload):
            log.error("Meta could not deliver a reply: %s", reason)
        log.info("POST /webhook: %d messages", len(msgs))
        # Reply inside the request: Cloud Run throttles CPU once a response is sent, so work
        # after the 200 can stall. Meta may retry a slow request; seen ids are answered once.
        for msg in msgs:
            if not msg.get("id") or seen.add(msg["id"]):
                await handle(msg)
        return {"ok": True}

    return app


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
app = create_app()
