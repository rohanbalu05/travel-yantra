"""One WhatsApp message -> POST {API_BASE_URL}/chat (the same chat engine as the web) -> the reply.

Voice notes are downloaded from the Cloud API here (only the bot holds WHATSAPP_TOKEN) and sent
to /chat as audio, where Gemini 3.1 Flash-Lite transcribes them. Conversation state lives in the
API (Cloud SQL), keyed by an id made from the sender's number with the app secret, so the id
can't be guessed from a phone number and holds no number itself.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from collections.abc import Awaitable, Callable

import httpx

from .sender import GRAPH, digits

log = logging.getLogger(__name__)
MAX_AUDIO_BYTES = 3_000_000  # /chat takes about 3 MB of audio
# Where Cloud API media URLs point (lookaside.fbsbx.com today); the token goes nowhere else.
META_HOSTS = (".fbsbx.com", ".fbcdn.net", ".whatsapp.net", ".facebook.com")
NOT_TEXT = "Sorry, I can read text, voice notes and locations. Please type your message."
TOO_LONG = "That voice note is too long for me. Please keep it under two minutes, or type it."
NO_MEDIA = "I could not download that voice note. Please send it again, or type your message."
OFFLINE = "The planner is not connected just now. Please try again later."
BUSY = "The planner is busy just now. Please try again in a minute."


def client_id(wa_id: str) -> str:
    """'wa-' + 40 hex characters; the same sender always gets the same conversation."""
    key = os.environ.get("WHATSAPP_APP_SECRET", "") or "ty-whatsapp"
    mac = hmac.new(key.encode(), digits(wa_id).encode(), hashlib.sha256).hexdigest()
    return "wa-" + mac[:40]


class Chat:
    """`handle(msg, notify, audio)` -> the reply text; notes ("Working on your plan", what a voice
    note said) go out early through `notify`, and story audio URLs are added to `audio`."""

    def __init__(self, base: str | None = None, token: str | None = None) -> None:
        base = base if base is not None else os.environ.get("API_BASE_URL", "")
        self.base = base.rstrip("/")
        self.token = token if token is not None else os.environ.get("WHATSAPP_TOKEN", "").strip()

    async def handle(
        self,
        msg: dict,
        notify: Callable[[str], Awaitable[None]] | None = None,
        audio: list[str] | None = None,
    ) -> str:
        kind = msg.get("type")
        body: dict = {"channel": "whatsapp"}
        if kind == "text":
            body["text"] = msg.get("text", {}).get("body", "")[:4000]
        elif kind == "location":
            loc = msg.get("location", {})
            body["location"] = {"lat": loc.get("latitude"), "lng": loc.get("longitude")}
        elif kind == "audio":
            media = msg.get("audio", {})
            got = await self.download(media.get("id", ""))
            if isinstance(got, str):
                return got
            data, mime = got
            body["audio"] = {
                "data": base64.b64encode(data).decode(),
                "mime": media.get("mime_type") or mime,
            }
        else:
            log.info("route: %s message (not handled)", kind)
            return NOT_TEXT
        if not self.base:
            return OFFLINE
        return await self.post(client_id(msg.get("from", "")), body, notify, audio)

    async def post(self, cid: str, body: dict, notify, audio: list[str] | None) -> str:
        parts: list[str] = []
        async with (
            httpx.AsyncClient(timeout=httpx.Timeout(200, connect=10)) as client,
            client.stream(
                "POST", f"{self.base}/chat", json=body, headers={"X-Client-Id": cid}
            ) as r,
        ):
            if r.is_error:
                await r.aread()
                log.error("POST /chat: HTTP %s", r.status_code)
                return BUSY
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue  # blank separators and ": ping" keep-alives
                event = json.loads(line[5:].strip())
                kind, text = event.get("type"), event.get("text") or ""
                if kind == "heard" and text and notify:
                    await notify(f"🎤 “{text}”")
                elif kind == "note" and text and notify:
                    await notify(text)
                elif kind in ("text", "error") and text:
                    parts.append(text)
                elif kind == "audio" and event.get("url") and audio is not None:
                    audio.append(event["url"])
                elif kind == "done":
                    break
        return "\n\n".join(parts)

    async def download(self, media_id: str) -> tuple[bytes, str] | str:
        """The voice note's bytes and type, or a message for the user when it can't be had."""
        if not self.token or not media_id:
            log.warning("voice note: WHATSAPP_TOKEN or the media id is missing")
            return NO_MEDIA
        auth = {"Authorization": f"Bearer {self.token}"}
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                meta = await client.get(f"{GRAPH}/{media_id}", headers=auth)
                meta.raise_for_status()
                info = meta.json()
                if int(info.get("file_size") or 0) > MAX_AUDIO_BYTES:
                    return TOO_LONG
                host = httpx.URL(info["url"]).host
                if not host.endswith(META_HOSTS):
                    # The token goes only to Meta's own media hosts.
                    log.error("voice note: media host is not Meta's")
                    return NO_MEDIA
                data = bytearray()
                async with client.stream("GET", info["url"], headers=auth) as r:
                    r.raise_for_status()
                    async for chunk in r.aiter_bytes():
                        data += chunk
                        if len(data) > MAX_AUDIO_BYTES:
                            return TOO_LONG
        except (httpx.HTTPError, ValueError, KeyError) as e:
            log.error("voice note download failed: %s", type(e).__name__)
            return NO_MEDIA
        log.info("voice note: %d bytes", len(data))
        return bytes(data), info.get("mime_type") or "audio/ogg"
