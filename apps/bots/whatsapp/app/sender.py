"""Send text replies through the WhatsApp Cloud API (or record them in tests)."""

from __future__ import annotations

import logging
import os
import re
from typing import Protocol

import httpx

GRAPH = "https://graph.facebook.com/v23.0"
log = logging.getLogger(__name__)
NOT_DIGIT = re.compile(r"\D")


class Sender(Protocol):
    async def send_text(self, to: str, body: str) -> None: ...


def digits(number: str) -> str:
    """'+91 98450-12345' -> '919845012345'; WhatsApp's wa_id is digits only."""
    return NOT_DIGIT.sub("", number).lstrip("0")


def allowed_recipients() -> set[str]:
    raw = os.environ.get("WHATSAPP_ALLOWED_RECIPIENTS", "")
    return {d for n in raw.replace(";", ",").replace("\n", ",").split(",") if (d := digits(n))}


def is_allowed(wa_id: str, allowed: set[str]) -> bool:
    """wa_id is country code + number; an allowed entry without the code (10 digits) means India."""
    to = digits(wa_id)
    return bool(to) and any(to == a or (len(a) == 10 and to == "91" + a) for a in allowed)


def graph_error(r: httpx.Response) -> str:
    """Code, subcode and type of a Graph API error; never the message, which can echo the number."""
    try:
        err = r.json().get("error", {})
    except ValueError:
        return f"HTTP {r.status_code}"
    if not isinstance(err, dict):
        return f"HTTP {r.status_code}"
    return (
        f"HTTP {r.status_code} code={err.get('code')} subcode={err.get('error_subcode')} "
        f"type={err.get('type')}"
    )


class CloudApiSender:
    """Replies via WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID, only to allowed recipients."""

    def __init__(self) -> None:
        self.token = os.environ.get("WHATSAPP_TOKEN", "").strip()
        self.phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
        self.allowed = allowed_recipients()
        log.info(
            "sender ready: %d allowed recipients, token %s, phone number id %s",
            len(self.allowed),
            "set" if self.token else "UNSET",
            "set" if self.phone_id else "UNSET",
        )

    async def send_text(self, to: str, body: str) -> None:
        if not is_allowed(to, self.allowed):
            log.warning(
                "not sending: recipient (%d digits) is not in WHATSAPP_ALLOWED_RECIPIENTS (%d entries)",
                len(digits(to)),
                len(self.allowed),
            )
            return
        if not self.token or not self.phone_id:
            log.warning("not sending: WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID is unset")
            return
        payload = {
            "messaging_product": "whatsapp",
            "to": digits(to),
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
            log.error("send failed: %s", graph_error(r))
        else:
            log.info("sent a reply of %d characters", len(body))


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, to: str, body: str) -> None:
        self.sent.append((to, body))
