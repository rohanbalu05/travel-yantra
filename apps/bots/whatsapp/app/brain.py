"""Turn one WhatsApp message into one reply: plan a trip, or ask the guide, in the user's language."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import httpx
from ty_contracts import (
    GuideAnswer,
    GuideQuestion,
    Itinerary,
    Lang,
    PlanEvent,
    PlanStage,
    PlanText,
    SeasonNote,
    TripDraft,
)

from .translate import Translator

SAMPLE = Path(__file__).parent / "samples/goa_family.json"
SAMPLE_PLAN_ID = "sample-goa"
MAX_REPLY = 4000  # WhatsApp text bodies are capped at 4096 characters
PENDING_SECONDS = 30 * 60  # how long the planner's follow-up questions stay open
LOCATION_SECONDS = 60 * 60  # how long a shared location is used for guide questions

HELP = (
    "Namaste! Tell me about your trip, for example:\n"
    "Plan Bengaluru to Goa, 11-14 Dec, 4 of us\n"
    "or ask me anything about a place, its food or its history. "
    "Share your location for help nearby. "
    "Send delete my data to make me forget you."
)
VOICE = (
    "Sorry, I can only read text messages for now. "
    "Please type your question and I will reply right away."
)
NOT_TEXT = "Sorry, I can only read text messages for now. Please type your message."
LOCATION_OK = "Got your location. Ask me, for example: nearest hospital or pharmacy."
ASKING = "To plan this I need a little more:"
PLANNING = "Working on your plan now; this takes about a minute."
CONTACT = "rohan@aizyantra.com"
FORGOTTEN = "Done. I have forgotten your plans, your language and your location."
FORGOTTEN_KEPT = (
    "Saved copies of your plans (behind their share links) could not be deleted from here; "
    f"email {CONTACT} and we will remove them."
)
FORGET = re.compile(
    r"^\s*(?:please\s+)?(?:delete|erase|remove|forget)\s+(?:all\s+)?(?:my\s+)?"
    r"(?:data|details|chats?|history|everything|me)\b"
    r"|डेटा\s*(?:हटा|मिटा|डिलीट)",
    re.IGNORECASE,
)
# Set per message by the webhook: sends an early note ("working on your plan") before a slow reply.
NOTIFY: ContextVar[Callable[[str], Awaitable[None]] | None] = ContextVar("notify", default=None)
GREETINGS = {
    "hi",
    "hello",
    "help",
    "namaste",
    "start",
    "नमस्ते",
    "ನಮಸ್ಕಾರ",
    "வணக்கம்",
    "నమస్కారం",
    "নমস্কার",
}
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


# Follow-ups once a plan exists. Keywords stay English in the hint so users can copy them.
_END = r"(?=\s|$|[.,!?])"
SHARE = re.compile(rf"^\s*(?:share|link|शेयर|ಹಂಚಿ|பகிர்|షేర్|শেয়ার){_END}", re.IGNORECASE)
LIGHTER = re.compile(rf"\b(?:lighter|easier|relaxed|halka){_END}|हल्का", re.IGNORECASE)
RAIN = re.compile(
    rf"\b(?:rain|raining|rainy|baarish|barish){_END}|बारिश|ಮಳೆ|மழை|వర్షం|বৃষ্টি", re.IGNORECASE
)
MOVE = re.compile(
    r"\b(?:(?:an?\s+)?(?:extra|another|one\s+more)\s+day|more\s+(?:time|days?)|add\s+a\s+day"
    r"|move\s+a\s+day)\s+(?:in|at|to|for)\s+(?P<city>[^\d?!.,]+)",
    re.IGNORECASE,
)
SWAP = re.compile(r"^\s*(?:swap|replace|skip|change)\s+(?P<what>.+)$", re.IGNORECASE)
DAY_N = re.compile(
    r"\bday\s*(?P<a>\d{1,2})\b|\b(?P<b>\d{1,2})(?:st|nd|rd|th)?\s+day\b", re.IGNORECASE
)
NEXT = "Reply share for a link, or: lighter day 2 · rain day 3 · swap <place>"
NEXT_KEEP = ["share", "lighter day 2", "rain day 3", "swap <place>"]
EXPIRED = "That plan has expired. Send your trip again and I will plan it afresh."
WHICH_DAY = "Which day? For example: lighter day 2"


def parse_followup(text: str) -> tuple[str, int | None, str | None] | None:
    """(intent, day number, stop or city) for share / lighter / rain / swap / move_day; else None."""
    if SHARE.search(text):
        return "share", None, None
    if text.rstrip().endswith(("?", "？")):
        return None  # "is it raining in Goa?" is a question for the guide
    if mv := MOVE.search(text):
        return "move_day", None, mv["city"].strip()
    m = DAY_N.search(text)
    n = int(m["a"] or m["b"]) if m else None
    if s := SWAP.match(text):
        return "swap_stop", n, s["what"].strip(" .")
    if RAIN.search(text):
        return "rain", n, None
    if LIGHTER.search(text):
        return "lighter_day", n, None
    return None


@dataclass
class Ask:
    """The planner's needs_input: up to three questions and what it understood so far."""

    questions: list[str]
    draft: TripDraft | None = None


def so_far(d: TripDraft | None) -> tuple[str, list[str]]:
    """'So far: Goa from Bengaluru, 11 Dec to 14 Dec, 4 travellers' and the names to keep."""
    if d is None:
        return "", []
    parts, keep = [], [*d.destinations, *([d.origin] if d.origin else [])]
    if d.destinations:
        parts.append(", ".join(d.destinations) + (f" from {d.origin}" if d.origin else ""))
    elif d.origin:
        parts.append(f"from {d.origin}")
    if d.start_date and d.end_date:
        parts.append(f"{d.start_date:%d %b} to {d.end_date:%d %b}")
    elif d.start_date:
        parts.append(f"from {d.start_date:%d %b}")
    if d.travellers:
        parts.append(f"{len(d.travellers)} travellers")
    if d.budget_inr:
        parts.append(f"budget ₹{d.budget_inr:,}")
    return ("So far: " + ", ".join(parts) if parts else ""), keep


class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


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
    lines.extend(f"Season, {n.city}: {n.text} [{i}]" for i, n in enumerate(season(it), 1))
    return "\n".join(lines)


def season(it: Itinerary, limit: int = 2) -> list[SeasonNote]:
    """TY2's quoted season notes, the trip's months first; numbered to match their sources."""
    return sorted(it.season_notes, key=lambda n: n.kind != "month")[:limit]


def season_sources(it: Itinerary) -> str:
    return "\n".join(f"[{i}] {n.source_url}" for i, n in enumerate(season(it), 1))


def next_hint(it: Itinerary) -> tuple[str, list[str]]:
    """The follow-up keywords, with "extra day in <city>" when the trip has several cities."""
    if len(it.request.destinations) < 2:
        return NEXT, NEXT_KEEP
    extra = f"extra day in {it.request.destinations[-1]}"
    return f"{NEXT} · {extra}", [*NEXT_KEEP, extra]


def names(it: Itinerary) -> list[str]:
    """Place names in a summary, kept untranslated (native names come from the translate service)."""
    req = it.request
    return [req.origin, *req.destinations, *(p.name for d in it.days for p in d.stops)]


def sources(answer: GuideAnswer) -> str:
    """Numbered to match the [n] markers in the answer text; never translated."""
    lines = [
        f"[{i}] {c.title}" + (f" {c.url}" if c.url else "")
        for i, c in enumerate(answer.citations, 1)
    ]
    lines += [
        f"{p.name} https://maps.google.com/?q={p.lat},{p.lng}" for p in answer.emergency_places
    ]
    return "\n".join(lines)


def _detail(r: httpx.Response) -> str:
    """The API's own words for an error ("plan not found", a 422's messages)."""
    try:
        detail = r.json().get("detail")
    except ValueError:
        detail = None
    if isinstance(detail, list):
        detail = "; ".join(str(d.get("msg", d)) for d in detail if isinstance(d, dict))
    return detail if isinstance(detail, str) and detail else f"HTTP {r.status_code}"


def _cap(text: str, limit: int = MAX_REPLY) -> str:
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


@dataclass
class User:
    lang: Lang = Lang.en
    pending: str | None = None  # original trip text while the planner waits for answers
    pending_at: float = 0.0
    lat: float | None = None
    lng: float | None = None
    located_at: float = 0.0
    itinerary: Itinerary | None = None  # the latest plan, for share and revise
    plan_id: str | None = None
    share_token: str | None = None
    plan_ids: list[str] = field(default_factory=list)  # every plan made, for delete my data


class Brain:
    """Calls the API at API_BASE_URL; without it, answers from the Goa sample.

    Per-user state (language, open planner questions, last location) lives in memory only.
    """

    def __init__(
        self, base: str | None = None, translator: Translator | None = None, clock=time.monotonic
    ):
        base = base if base is not None else os.environ.get("API_BASE_URL", "")
        self.base = base.rstrip("/")
        self.tr = translator or Translator()
        self.clock = clock
        self.users: dict[str, User] = {}

    async def handle(
        self, msg: dict, notify: Callable[[str], Awaitable[None]] | None = None
    ) -> str:
        """The reply to one message; `notify` sends an early note while a plan is being made."""
        token = NOTIFY.set(notify)
        try:
            return await self._handle(msg)
        finally:
            NOTIFY.reset(token)

    async def _handle(self, msg: dict) -> str:
        who, kind = msg.get("from", ""), msg.get("type")
        body = msg.get("text", {}).get("body", "") if kind == "text" else ""
        if FORGET.search(body):
            return await self.forget(who, detect_lang(body))
        user = self.users.setdefault(who, User())
        if kind == "text":
            return await self.reply(user, body)
        if kind == "location":
            loc = msg.get("location", {})
            user.lat, user.lng = loc.get("latitude"), loc.get("longitude")
            user.located_at = self.clock()
            return await self.say(user, LOCATION_OK)
        return await self.say(user, VOICE if kind == "audio" else NOT_TEXT)

    async def forget(self, who: str, lang: Lang) -> str:
        """Drop everything kept for this sender and delete the plans they made through the API."""
        user = self.users.pop(who, None) or User()
        failed = 0
        for plan_id in dict.fromkeys(user.plan_ids):
            failed += not await self.delete_plan(plan_id)
        english = FORGOTTEN + (" " + FORGOTTEN_KEPT if failed else "")
        return await self.say(User(lang=lang), english, keep=[CONTACT])

    async def delete_plan(self, plan_id: str) -> bool:
        """DELETE /plan/{plan_id} (TY1); a 404 means it is already gone. False when it failed."""
        if not self.base or plan_id == SAMPLE_PLAN_ID:
            return True  # offline sample plans are never saved
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.delete(f"{self.base}/plan/{quote(plan_id, safe='')}")
        except httpx.HTTPError:
            return False
        if r.status_code == 404:
            # Already gone, or the endpoint is not deployed yet: then 404 says "Not Found".
            return _detail(r) != "Not Found"
        return r.is_success

    async def working(self, user: User) -> None:
        """Tell the user a slow plan is under way (only against the real API)."""
        if self.base and (notify := NOTIFY.get()):
            await notify(await self.tr.text(PLANNING, user.lang))

    async def say(self, user: User, english: str, keep: list[str] = (), tail: str = "") -> str:
        body = await self.tr.text(english, user.lang, keep) if english else ""
        if not tail:
            return _cap(body)
        if not body:
            return _cap(tail)
        # Cap the body, not the sources: [n] markers must keep their list.
        return _cap(_cap(body, MAX_REPLY - len(tail) - 2) + "\n\n" + tail)

    async def reply(self, user: User, text: str) -> str:
        text = text.strip()
        waiting = bool(user.pending) and self.clock() - user.pending_at < PENDING_SECONDS
        if text:
            lang = detect_lang(text)
            # A short Latin answer ("4 people, train") keeps a Hindi user's language mid-plan.
            if lang != Lang.en or not waiting:
                user.lang = lang
        if not text or text.lower() in GREETINGS:
            return await self.say(user, HELP)
        if text.lower() in CANCEL:
            user.pending = None
            return await self.say(user, HELP)
        follow = parse_followup(text) if user.itinerary is not None else None
        if follow and follow[0] == "swap_stop" and not text.lower().lstrip().startswith("swap"):
            # "change my dates", "replace the hotel": a swap only if it names a stop in the plan
            stops = [p.name.casefold() for d in user.itinerary.days for p in d.stops]
            if not any(follow[2] and follow[2].casefold() in s for s in stops):
                follow = None
        if follow:
            return await self.followup(user, *follow)
        if is_trip(text):
            return await self.trip(user, text)  # a fresh trip replaces any open questions
        if waiting and not text.endswith(("?", "？")):
            return await self.trip(user, user.pending + "\n" + text)
        answer = await self.ask(user, text)  # questions still go to the guide mid-plan
        return await self.say(user, answer.text, tail=sources(answer))

    async def trip(self, user: User, text: str) -> str:
        before = user.pending, user.pending_at
        user.pending = None
        await self.working(user)
        try:
            result = await self.plan(PlanText(text=text[:4000], lang=user.lang))
        except Exception:
            user.pending, user.pending_at = before  # the user can just try their answer again
            raise
        if isinstance(result, Ask):
            user.pending, user.pending_at = text, self.clock()
            known, keep = so_far(result.draft)
            lines = [ASKING, *(f"- {q}" for q in result.questions)]
            return await self.say(user, "\n".join(([known] if known else []) + lines), keep=keep)
        return await self.planned(user, *result)

    async def planned(
        self, user: User, it: Itinerary, plan_id: str | None, token: str | None
    ) -> str:
        user.itinerary, user.plan_id, user.share_token = it, plan_id, token
        if plan_id:
            user.plan_ids.append(plan_id)
        hint, keep = next_hint(it)
        return await self.say(
            user, summarise(it) + "\n\n" + hint, keep=names(it) + keep, tail=season_sources(it)
        )

    async def followup(self, user: User, intent: str, n: int | None, stop: str | None) -> str:
        it = user.itinerary
        if intent == "share":
            if not user.share_token:
                return await self.say(
                    user, "Sharing needs a saved plan; plan your trip again first."
                )
            web = os.environ.get("SHARE_BASE_URL", "").rstrip("/")
            # The web's read-only page (TY4); without it, the API's JSON for the same plan.
            link = (
                f"{web}/t/{user.share_token}/" if web else f"{self.base}/trips/{user.share_token}"
            )
            return await self.say(user, "Your plan:", tail=link)
        days = it.days
        if n is not None and not 1 <= n <= len(days):
            return await self.say(user, f"Your plan has days 1 to {len(days)}. {WHICH_DAY}")
        if intent == "lighter_day" and n is None:
            return await self.say(user, WHICH_DAY)
        body: dict = {"intent": intent, "lang": user.lang.value}
        if intent == "move_day":
            cities = it.request.destinations
            found = [c for c in cities if stop and stop.casefold() in c.casefold()]
            found = found or [c for c in cities if stop and c.casefold() in stop.casefold()]
            if not found:
                return await self.say(
                    user,
                    f"{stop} is not a city of this trip. Cities: {', '.join(cities)}",
                    keep=[stop or "", *cities],
                )
            body["city"] = found[0]
        if n is not None:
            body["day"] = days[n - 1].date.isoformat()
        if intent == "swap_stop":
            pool = days[n - 1].stops if n is not None else [p for d in days for p in d.stops]
            match = [p for p in pool if stop and stop.casefold() in p.name.casefold()]
            if not match:
                listed = ", ".join(p.name for p in pool)
                return await self.say(
                    user,
                    f"I could not find {stop} in your plan. Stops: {listed}",
                    keep=[stop or "", *(p.name for p in pool)],
                )
            body["place_id"] = match[0].id
        await self.working(user)
        try:
            result = await self.revise(user.plan_id, body)
        except ApiError as e:
            if e.status == 404:
                user.itinerary = user.plan_id = user.share_token = None
                return await self.say(user, EXPIRED)
            return await self.say(user, e.detail)
        return await self.planned(user, *result)

    async def plan(self, body: PlanText) -> tuple[Itinerary, str | None, str | None] | Ask:
        """(itinerary, plan_id, share_token), or the planner's follow-up questions (needs_input)."""
        if not self.base:
            sample = json.loads(SAMPLE.read_text(encoding="utf-8"))["itinerary"]
            it = Itinerary.model_validate(sample)
            it = it.model_copy(update={"warnings": [*it.warnings, "offline sample plan"]})
            return it, SAMPLE_PLAN_ID, None
        return await self._stream("/plan", body.model_dump(mode="json"))

    async def revise(
        self, plan_id: str | None, body: dict
    ) -> tuple[Itinerary, str | None, str | None]:
        if not self.base or not plan_id or plan_id == SAMPLE_PLAN_ID:
            sample = json.loads(SAMPLE.read_text(encoding="utf-8"))["itinerary"]
            it = Itinerary.model_validate(sample)
            it = it.model_copy(update={"warnings": [*it.warnings, "offline sample: not revised"]})
            return it, SAMPLE_PLAN_ID, None
        result = await self._stream(f"/plan/{quote(plan_id, safe='')}/revise", body)
        if isinstance(result, Ask):  # revise does not ask questions; treat it as a failure
            raise ApiError(422, " ".join(result.questions))
        return result

    async def _stream(self, path: str, body: dict):
        final = None
        async with (
            httpx.AsyncClient(timeout=120) as client,
            client.stream("POST", f"{self.base}{path}", json=body) as r,
        ):
            if r.is_error:
                await r.aread()
                raise ApiError(r.status_code, _detail(r))
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue  # blank separators and ": ping" keep-alives
                event = PlanEvent.model_validate_json(line[5:].strip())
                if event.stage == PlanStage.error:
                    raise RuntimeError(event.message)
                if event.stage == PlanStage.needs_input:
                    return Ask(event.questions, event.draft)
                if event.partial is not None:
                    final = event.partial
                if event.stage == PlanStage.done:
                    if final is None:
                        break
                    return final, event.plan_id, event.share_token
        raise RuntimeError("plan finished without an itinerary")

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
            r = await client.post(
                f"{self.base}/guide/ask", json=q.model_dump(mode="json", exclude_none=True)
            )
            r.raise_for_status()
            return GuideAnswer.model_validate(r.json())
