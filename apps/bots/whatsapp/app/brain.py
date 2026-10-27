"""Turn one WhatsApp message into one reply: plan a trip, or ask the guide, in the user's language."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from ty_contracts import (
    GuideAnswer,
    GuideQuestion,
    Itinerary,
    Lang,
    PlanEvent,
    PlanStage,
    PlanText,
)

from .translate import Translator

SAMPLE = Path(__file__).parent / "samples/goa_family.json"
MAX_REPLY = 4000  # WhatsApp text bodies are capped at 4096 characters
PENDING_SECONDS = 30 * 60  # how long the planner's follow-up questions stay open
LOCATION_SECONDS = 60 * 60  # how long a shared location is used for guide questions

HELP = (
    "Namaste! Tell me about your trip, for example:\n"
    "Plan Bengaluru to Goa, 11-14 Dec, 4 of us\n"
    "or ask me anything about a place, its food or its history. "
    "Share your location for help nearby."
)
VOICE = (
    "Sorry, I can only read text messages for now. "
    "Please type your question and I will reply right away."
)
NOT_TEXT = "Sorry, I can only read text messages for now. Please type your message."
LOCATION_OK = "Got your location. Ask me, for example: nearest hospital or pharmacy."
ASKING = "To plan this I need a little more:"
GREETINGS = {"hi", "hello", "help", "namaste", "start", "नमस्ते", "ನಮಸ್ಕಾರ", "வணக்கம்", "నమస్కారం", "নমস্কার"}
CANCEL = {"cancel", "stop", "new", "reset"}

# Unicode blocks of the Indic scripts we support; Hinglish (Latin script) counts as English.
SCRIPTS = {
    Lang.hi: (0x0900, 0x097F),
    Lang.bn: (0x0980, 0x09FF),
    Lang.ta: (0x0B80, 0x0BFF),
    Lang.te: (0x0C00, 0x0C7F),
    Lang.kn: (0x0C80, 0x0CFF),
}

_MONTH = r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
# Trip words in English, Hinglish and the five Indic scripts.
TRIP_WORDS = re.compile(
    r"\b(?:plan|trip|itinerary|holiday|vacation|tour|yatra|safar)\b"
    r"|यात्रा|सफ़र|सफर|घूमने|ಪ್ರವಾಸ|ಯಾತ್ರೆ|பயண|சுற்றுலா|ప్రయాణ|యాత్ర|పర్యటన|ভ্রমণ|বেড়াতে|যাত্রা",
    re.IGNORECASE,
)
# "Bengaluru to Goa" / "Bengaluru se Goa" together with a date: a trip even without a trip word.
ROUTE = re.compile(r"[A-Za-z]\s+(?:to|se)\s+[A-Za-z]", re.IGNORECASE)
DATE = re.compile(rf"\d|\b(?:{_MONTH})", re.IGNORECASE)


def detect_lang(text: str) -> Lang:
    counts = {lang: 0 for lang in SCRIPTS}
    for ch in text:
        for lang, (lo, hi) in SCRIPTS.items():
            if lo <= ord(ch) <= hi:
                counts[lang] += 1
    lang, n = max(counts.items(), key=lambda kv: kv[1])
    return lang if n else Lang.en


def is_trip(text: str) -> bool:
    return bool(TRIP_WORDS.search(text) or (ROUTE.search(text) and DATE.search(text)))


def summarise(it: Itinerary) -> str:
    req = it.request
    head = f"{', '.join(req.destinations)} from {req.origin}, "
    lines = [head + f"{req.start_date:%d %b} to {req.end_date:%d %b}"]
    for i, day in enumerate(it.days, start=1):
        stops = ", ".join(p.name for p in day.stops) or "rest day"
        lines.append(f"Day {i} ({day.date:%a %d %b}): {stops}")
    for opt in it.transport[:3]:
        hours = opt.total_minutes / 60
        lines.append(f"{opt.mode.value.title()}: {hours:.1f} h, ₹{opt.total_cost_inr:,}")
    lines.append(f"Budget: ₹{it.budget.total_inr:,} total")
    lines.extend(f"Note: {w}" for w in it.warnings)
    return "\n".join(lines)


def names(it: Itinerary) -> list[str]:
    """Place names in a summary, kept untranslated (native names come from the translate service)."""
    req = it.request
    return [req.origin, *req.destinations, *(p.name for d in it.days for p in d.stops)]


def sources(answer: GuideAnswer) -> str:
    """Numbered to match the [n] markers in the answer text; never translated."""
    lines = [f"[{i}] {c.title}" + (f" {c.url}" if c.url else "") for i, c in enumerate(answer.citations, 1)]
    lines += [
        f"{p.name} https://maps.google.com/?q={p.lat},{p.lng}" for p in answer.emergency_places
    ]
    return "\n".join(lines)


def _cap(text: str) -> str:
    return text if len(text) <= MAX_REPLY else text[: MAX_REPLY - 1] + "…"


@dataclass
class User:
    lang: Lang = Lang.en
    pending: str | None = None  # original trip text while the planner waits for answers
    pending_at: float = 0.0
    lat: float | None = None
    lng: float | None = None
    located_at: float = 0.0


class Brain:
    """Calls the API at API_BASE_URL; without it, answers from the Goa sample.

    Per-user state (language, open planner questions, last location) lives in memory only.
    """

    def __init__(self, base: str | None = None, translator: Translator | None = None, clock=time.monotonic):
        base = base if base is not None else os.environ.get("API_BASE_URL", "")
        self.base = base.rstrip("/")
        self.tr = translator or Translator()
        self.clock = clock
        self.users: dict[str, User] = {}

    async def handle(self, msg: dict) -> str:
        user = self.users.setdefault(msg.get("from", ""), User())
        kind = msg.get("type")
        if kind == "text":
            return await self.reply(user, msg.get("text", {}).get("body", ""))
        if kind == "location":
            loc = msg.get("location", {})
            user.lat, user.lng = loc.get("latitude"), loc.get("longitude")
            user.located_at = self.clock()
            return await self.say(user, LOCATION_OK)
        return await self.say(user, VOICE if kind == "audio" else NOT_TEXT)

    async def say(self, user: User, english: str, keep: list[str] = (), tail: str = "") -> str:
        body = await self.tr.text(english, user.lang, keep) if english else ""
        return _cap(body + (f"\n\n{tail}" if tail and body else tail))

    async def reply(self, user: User, text: str) -> str:
        text = text.strip()
        if text:
            user.lang = detect_lang(text)
        if not text or text.lower() in GREETINGS:
            return await self.say(user, HELP)
        if text.lower() in CANCEL:
            user.pending = None
            return await self.say(user, HELP)
        if user.pending and self.clock() - user.pending_at < PENDING_SECONDS:
            return await self.trip(user, user.pending + "\n" + text)
        if is_trip(text):
            return await self.trip(user, text)
        answer = await self.ask(user, text)
        return await self.say(user, answer.text, tail=sources(answer))

    async def trip(self, user: User, text: str) -> str:
        user.pending = None
        result = await self.plan(PlanText(text=text[:4000], lang=user.lang))
        if isinstance(result, list):
            user.pending, user.pending_at = text, self.clock()
            return await self.say(user, "\n".join([ASKING, *(f"- {q}" for q in result)]))
        return await self.say(user, summarise(result), keep=names(result))

    async def plan(self, body: PlanText) -> Itinerary | list[str]:
        """The itinerary, or the planner's follow-up questions (needs_input)."""
        if not self.base:
            sample = json.loads(SAMPLE.read_text(encoding="utf-8"))["itinerary"]
            it = Itinerary.model_validate(sample)
            return it.model_copy(update={"warnings": [*it.warnings, "offline sample plan"]})
        final = None
        async with (
            httpx.AsyncClient(timeout=120) as client,
            client.stream("POST", f"{self.base}/plan", json=body.model_dump(mode="json")) as r,
        ):
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue  # blank separators and ": ping" keep-alives
                event = PlanEvent.model_validate_json(line[5:].strip())
                if event.stage == PlanStage.error:
                    raise RuntimeError(event.message)
                if event.stage == PlanStage.needs_input:
                    return event.questions
                if event.partial is not None:
                    final = event.partial
                if event.stage == PlanStage.done:
                    break
        if final is None:
            raise RuntimeError("plan finished without an itinerary")
        return final

    async def ask(self, user: User, question: str) -> GuideAnswer:
        located = user.lat is not None and self.clock() - user.located_at < LOCATION_SECONDS
        q = GuideQuestion(
            question=question[:500],
            lang=user.lang,
            lat=user.lat if located else None,
            lng=user.lng if located else None,
        )
        if not self.base:
            return GuideAnswer(text=f"(offline sample) I would ask the guide: {question}")
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{self.base}/guide/ask", json=q.model_dump(mode="json", exclude_none=True))
            r.raise_for_status()
            return GuideAnswer.model_validate(r.json())
