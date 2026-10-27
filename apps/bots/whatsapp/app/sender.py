"""Send text replies through the WhatsApp Cloud API (or record them in tests)."""

from __future__ import annotations

import logging
import os
from typing import Protocol

import httpx

GRAPH = "https://graph.facebook.com/v23.0"
log = logging.getLogger(__name__)


class Sender(Protocol):
    async def send_text(self, to: str, body: str) -> None: ...


class CloudApiSender:
    """Replies via WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID, only to allowed recipients."""

    def __init__(self) -> None:
        self.token = os.environ.get("WHATSAPP_TOKEN", "")
        self.phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
        self.allowed = allowed_recipients()

    async def send_text(self, to: str, body: str) -> None:
        if to not in self.allowed:
            log.warning("not sending: recipient is not in WHATSAPP_ALLOWED_RECIPIENTS")
            return
        if not self.token or not self.phone_id:
            log.warning("not sending: WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID is unset")
            return
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body, "preview_url": False},
        }
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{GRAPH}/{self.phone_id}/messages",
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"},
            )
        if r.is_error:
            # Status only: the body can echo the recipient's number.
            log.error("send failed: HTTP %s", r.status_code)


def allowed_recipients() -> set[str]:
    raw = os.environ.get("WHATSAPP_ALLOWED_RECIPIENTS", "")
    return {n.strip().lstrip("+") for n in raw.split(",") if n.strip()}


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, to: str, body: str) -> None:
        self.sent.append((to, body))
