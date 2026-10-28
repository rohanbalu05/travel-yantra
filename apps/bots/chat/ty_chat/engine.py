"""One chat engine for the web chat panel and WhatsApp: a message in, reply events out.

The routing, in order: voice note -> its words; delete my data; location; greeting; cancel the
trip; a story; then the trip being drafted (answers add to it; only a whole trip to a different
place starts a new one), a new trip, an edit to the current plan (keyword rules, else one
Flash-Lite parse), and last the guide.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import os
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ty_contracts import (
    GuideAnswer,
    GuideQuestion,
    Itinerary,
    KathaRequest,
    Lang,
    Leg,
    PlanEvent,
    PlanStage,
    SeasonNote,
    TripDraft,
)

from . import text as rules
from .api import Api, ApiError, Ask, Planned
from .lite import Edit, Lite, get_lite
from .models import Audio, ChatEvent, ChatIn, Conversation
from .store import Store, get_store
from .translate import Translator

log = logging.getLogger(__name__)
MAX_TOTAL = 12_000  # one reply; WhatsApp splits it into 4,000-character messages
DRAFT_SECONDS = 30 * 60  # how long a trip being put together stays open
LOCATION_SECONDS = 60 * 60  # how long a shared location is used for guide questions
IST = timezone(timedelta(hours=5, minutes=30))

HELP = (
    "Namaste! Tell me about your trip, for example:\n"
    "Plan Bengaluru to Goa, 11-14 Dec, 4 of us\n"
    "or ask me anything about a place, its food or its history. "
    "For a place's story, send: story Mysore Palace. "
    "Share your location for help nearby. "
    "Send delete my data to make me forget you."
)
HELP_CHIPS = ["Plan Bengaluru to Goa, 11-14 Dec, 4 of us", "story Mysore Palace", "nearest hospital"]
LOCATION_OK = "Got your location. Ask me, for example: nearest hospital or pharmacy."
ASKING = "To plan this I need a little more:"
PLANNING = "Working on your plan now; this takes about a minute."
REVISING = "Changing your plan; this takes a few seconds."
FINDING_STORY = "Finding the story; this takes a few seconds."
CANCELLED = "Okay, I have closed that trip. Tell me about the next one whenever you like."
NOTHING_OPEN = "There is no trip open just now. Tell me where you would like to go."
NOT_HEARD = "I could not make out any words in that voice note. Please try again, or type it."
BAD_AUDIO = "I could not open that voice note. Please send it again, or type your message."
HEARING_FAILED = "I could not listen to that voice note just now. Please type your message."
PLAN_FAILED = "I could not make that plan just now: {why}. Please try again in a minute."
BUSY = "The planner is busy just now. Please try again in a minute."
SORRY = "Sorry, something went wrong on our side. Please try again in a minute."
SAME_PLACE = (
    "You already have a plan for {where}. Tell me what to change (for example: lighter day 2), "
    "or name a different place for a new trip."
)
CANT_EDIT = (
    "I could not tell what to change. Try for example: lighter day 2, swap {stop}, "
    "add a stop on day 1, cheaper hotel, by train, or running late 30 min."
)
NO_PLAN = (
    "You have no plan yet. Send your trip first, for example: "
    "Plan Bengaluru to Mysuru, 31 Oct to 1 Nov, 2 of us"
)
EXPIRED = "That plan has expired. Send your trip again and I will plan it afresh."
WHICH_DAY = "Which day? For example: lighter day 2"
NOT_FOUND = "I could not find {what} in your plan. Stops: {stops}"
NOT_A_CITY = "{what} is not a city of this trip. Cities: {cities}"
NO_STORY = "I have no story for {what} yet. Try another place, for example: story Mysore Palace"
STORY_BUSY = "The storyteller is busy just now. Please try again in a minute."
CONTACT = "rohan@aizyantra.com"
FORGOTTEN = "Done. I have forgotten our chat, your language and your location, and deleted {n}."
FORGOTTEN_NONE = "Done. I have forgotten our chat, your language and your location; I hold no plans."
FORGOTTEN_KEPT = f"If a plan link of yours still opens, email {CONTACT} with it and we will delete it."
NEXT = "Reply share for a link, or: lighter day 2 · rain day 3 · swap <place> · add <place>"
NEXT_CHIPS = ["share", "lighter day 2", "rain day 3", "cheaper hotel", "running late 30 min"]
CHANGED = {
    "lighter_day": "Made day {day} lighter.",
    "swap_stop": "Swapped {place}.",
    "rain": "Moved to indoor places for the rain.",
    "move_day": "Gave {city} one more day.",
    "transport": "Switched the journeys to {mode}.",
    "add_stop": "Added {place}.",
    "remove_stop": "Removed {place}.",
    "move_stop": "Moved {place} to day {day}.",
    "change_stay": "Changed the stay.",
    "budget_style": "Switched to a {style} budget.",
    "booked": "Fitted the plan around your booked journey.",
    "rest_of_day": "Re-planned the rest of today from now.",
}
MODE_WORDS = {"rail": "train", "air": "flight", "road": "road"}
Emit = Callable[[ChatEvent], Awaitable[None]]


def _cap(text: str, limit: int = MAX_TOTAL) -> str:
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


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


def journeys(it: Itinerary) -> list[Leg]:
    """Every journey of the trip in order: out, between cities, home."""
    legs = [
        leg for d in it.days for leg in d.legs if leg.role in ("outbound", "between", "home")
    ]
    if legs:
        return legs
    return list(it.transport[0].legs) if it.transport else []


def _leg_line(leg: Leg) -> str:
    mode = MODE_WORDS.get(leg.mode.value, leg.mode.value)
    ref = f" {leg.ref}" if leg.ref else ""
    when = f"{leg.depart:%a %d %b %H:%M}"
    arrive = f"{leg.arrive:%H:%M}" if leg.arrive.date() == leg.depart.date() else (
        f"{leg.arrive:%a %d %b %H:%M}"
    )
    return (
        f"- {leg.from_} → {leg.to}: {mode}{ref}, {when} to {arrive}, "
        f"₹{leg.cost_inr:,} per person"
    )


def chosen_mode(it: Itinerary) -> str:
    """'Travel: by train (your choice)' or with the planner's reason."""
    mode = it.request.transport_mode or (it.transport[0].mode if it.transport else None)
    if mode is None:
        legs = journeys(it)
        mode = legs[0].mode if legs else None
    if mode is None:
        return ""
    word = MODE_WORDS.get(mode.value, mode.value)
    if it.request.transport_mode is not None:
        return f"Travel: by {word} (your choice)"
    return f"Travel: by {word}" + (f". {it.transport_reason}" if it.transport_reason else "")


def summarise(it: Itinerary) -> str:
    req = it.request
    people = len(req.constraints.travellers)
    head = f"{', '.join(req.destinations)} from {req.origin}, {req.start_date:%d %b} to "
    lines = [head + f"{req.end_date:%d %b}" + (f", {people} travellers" if people else "")]
    if mode := chosen_mode(it):
        lines.append(mode)
    if legs := journeys(it):
        lines.append("Journeys:")
        lines.extend(_leg_line(leg) for leg in legs)
    for i, day in enumerate(it.days, start=1):
        stops = ", ".join(p.name for p in day.stops) or "rest day"
        lines.append(f"Day {i} ({day.date:%a %d %b}): {stops}")
        lines.extend(f"  Note: {n}" for n in day.notes[:2])
    for s in it.stays[: len(req.destinations)]:
        lines.append(f"Stay in {s.city}: {s.name}, ₹{s.price_per_night_inr:,} a night for the party")
    total = f"Budget: ₹{it.budget.total_inr:,} total"
    lines.append(total + (f" for {people} travellers" if people else ""))
    lines.extend(f"Note: {w}" for w in it.warnings)
    lines.extend(f"Season, {n.city}: {n.text} [{i}]" for i, n in enumerate(season(it), 1))
    return "\n".join(lines)


def season(it: Itinerary, limit: int = 2) -> list[SeasonNote]:
    """TY2's quoted season notes, the trip's months first; numbered to match their sources."""
    return sorted(it.season_notes, key=lambda n: n.kind != "month")[:limit]


def season_sources(it: Itinerary) -> str:
    return "\n".join(f"[{i}] {n.source_url}" for i, n in enumerate(season(it), 1))


def names(it: Itinerary) -> list[str]:
    """Place names in a summary, kept untranslated."""
    req = it.request
    legs = [n for leg in journeys(it) for n in (leg.from_, leg.to)]
    stays = [s.name for s in it.stays]
    return [req.origin, *req.destinations, *legs, *stays, *(p.name for d in it.days for p in d.stops)]


def next_hint(it: Itinerary) -> tuple[str, list[str]]:
    """The follow-up keywords, with "extra day in <city>" when the trip has several cities."""
    if len(it.request.destinations) < 2:
        return NEXT, NEXT_CHIPS
    extra = f"extra day in {it.request.destinations[-1]}"
    return f"{NEXT} · {extra}", [*NEXT_CHIPS, extra]


def sources(answer: GuideAnswer) -> str:
    """Numbered to match the [n] markers in the answer text; never translated. Nearby places
    follow once each, numbered on, one per line, with a short map link (4 decimals is ~10 m)."""
    lines = [
        f"[{i}] {c.title}" + (f" {c.url}" if c.url else "")
        for i, c in enumerate(answer.citations, 1)
    ]
    used = [int(m) for m in re.findall(r"\[(\d{1,3})\]", answer.text)]
    first = max([len(lines), *used]) + 1
    seen, places = set(), []
    for p in answer.emergency_places:
        key = (p.name.casefold(), round(p.lat, 4), round(p.lng, 4))
        if key not in seen:
            seen.add(key)
            places.append(p)
    lines += [
        f"[{i}] {p.name} https://maps.google.com/?q={round(p.lat, 4)},{round(p.lng, 4)}"
        for i, p in enumerate(places, first)
    ]
    return "\n".join(lines)


@dataclass
class Turn:
    """One message being answered."""

    conv: Conversation
    emit: Emit
    plan_changed: bool = False
    forgotten: bool = False


class Engine:
    def __init__(
        self,
        api: Api,
        store: Store | None = None,
        translator: Translator | None = None,
        lite: Lite | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.api = api
        self.store = store or get_store()
        self.tr = translator or Translator()
        self.lite = lite
        self.clock = clock

    # --- the stream ---------------------------------------------------------------------

    async def chat(self, cid: str, body: ChatIn) -> AsyncIterator[ChatEvent]:
        """The events for one message; the conversation is saved before done is sent."""
        queue: asyncio.Queue[ChatEvent | None] = asyncio.Queue()
        task = asyncio.create_task(self._run(cid, body, queue.put))
        task.add_done_callback(lambda t: queue.put_nowait(None))
        # A caller who leaves mid-plan does not cancel the task: its answer is still saved.
        while (event := await queue.get()) is not None:
            yield event

    async def _run(self, cid: str, body: ChatIn, emit: Emit) -> None:
        async with _lock(cid):
            conv = await self.store.get(cid) or Conversation()
            turn = Turn(conv, emit)
            try:
                await self.handle(turn, body)
            except Exception:
                log.exception("chat reply failed (%s)", body.channel)
                await emit(ChatEvent(type="error", text=await self._tr(SORRY, conv.lang)))
            if turn.forgotten:
                await self.store.delete(cid)
            else:
                await self.store.put(cid, conv)
            await emit(
                ChatEvent(
                    type="done",
                    plan_id=conv.plan_id,
                    share_token=conv.share_token,
                    plan_changed=turn.plan_changed,
                    lang=conv.lang,
                )
            )

    # --- replies ------------------------------------------------------------------------

    async def _tr(self, english: str, lang: Lang, keep: list[str] = ()) -> str:
        return await self.tr.text(english, lang, list(keep)) if english else ""

    async def say(
        self, t: Turn, english: str, keep: list[str] = (), tail: str = "", chips=None
    ) -> None:
        body = await self._tr(english, t.conv.lang, keep)
        if tail:
            # Cap the body, not the sources: [n] markers must keep their list.
            body = _cap(body, MAX_TOTAL - len(tail) - 2) + "\n\n" + tail if body else tail
        await t.emit(ChatEvent(type="text", text=_cap(body)))
        if chips:
            await t.emit(ChatEvent(type="chips", chips=list(chips)))

    async def note(self, t: Turn, english: str) -> None:
        if not self.api.offline:
            await t.emit(ChatEvent(type="note", text=await self._tr(english, t.conv.lang)))

    def drafting(self, c: Conversation) -> bool:
        return bool(c.draft) and self.clock() - c.draft_at < DRAFT_SECONDS

    async def handle(self, t: Turn, body: ChatIn) -> None:
        c = t.conv
        text = body.text.strip()
        if body.audio is not None:
            if body.lang:
                c.lang = body.lang
            heard = await self.hear(t, body.audio)
            if heard is None:
                return
            text = f"{text}\n{heard}".strip() if text else heard
        if rules.FORGET.search(text):
            log.info("route: delete my data")
            return await self.forget(t, body.lang or rules.detect_lang(text))
        if body.lang:
            c.lang = body.lang
        elif text:
            lang = rules.detect_lang(text)
            # A short Latin answer ("4 people, train") keeps a Hindi user's language mid-trip.
            if lang != Lang.en or not self.drafting(c):
                c.lang = lang
        if body.location is not None:
            c.lat, c.lng, c.located_at = body.location.lat, body.location.lng, self.clock()
            if not text:
                return await self.say(t, LOCATION_OK)
        if body.plan_id and body.plan_id != c.plan_id:
            await self.adopt(c, body.plan_id, body.share_token)
        if not text or text.lower().strip(" !.") in rules.GREETINGS:
            return await self.say(t, HELP, chips=HELP_CHIPS)
        if rules.CANCEL.match(text):
            log.info("route: cancel")
            open_ = self.drafting(c)
            c.draft, c.draft_names = [], []
            return await self.say(t, CANCELLED if open_ else NOTHING_OPEN, chips=HELP_CHIPS[:1])
        if story := rules.parse_story(text):
            log.info("route: story (%d min)", story[1])
            return await self.story(t, *story)
        if self.drafting(c):
            new = [d for d in rules.destinations(text) if not rules.same_place(d, c.draft_names)]
            if rules.is_full_trip(text) and new:
                log.info("route: new trip replaces the draft")
                return await self.trip(t, [text])
            if rules.is_question(text) and not rules.is_trip(text):
                log.info("route: guide mid-draft")
                return await self.guide(t, text)
            log.info("route: draft answer")
            return await self.trip(t, [*c.draft, text])
        if rules.is_trip(text):
            places = c.itinerary.request.destinations if c.itinerary else []
            named = rules.destinations(text)
            new = [d for d in named if not rules.same_place(d, places)]
            if c.itinerary is None or new or rules.is_full_trip(text):
                log.info("route: plan")
                return await self.trip(t, [text])
        return await self.change_or_ask(t, text)

    async def change_or_ask(self, t: Turn, text: str) -> None:
        c = t.conv
        edit = rules.keyword_edit(text)
        if c.itinerary is None:
            if edit and len(text.split()) <= 6:
                log.info("route: edit %s without a plan", edit[0])
                return await self.say(t, NO_PLAN)
            return await self.guide(t, text)
        if edit is None and not rules.is_question(text):
            parsed = await self.parse_edit(c.itinerary, text)
            if parsed.intent != "none":
                edit = from_model(parsed)
                edit = None if edit[0] == "none" else edit
            elif rules.is_trip(text):
                where = ", ".join(c.itinerary.request.destinations)
                return await self.say(t, SAME_PLACE.format(where=where), keep=[where])
        if edit is None:
            return await self.guide(t, text)
        log.info("route: edit %s", edit[0])
        return await self.edit(t, *edit)

    async def parse_edit(self, it: Itinerary, text: str) -> Edit:
        lite = self.lite or get_lite()
        plan = "\n".join(
            [f"Cities: {', '.join(it.request.destinations)}"]
            + [
                f"Day {i} ({d.date:%a %d %b}): " + (", ".join(p.name for p in d.stops) or "rest")
                for i, d in enumerate(it.days, 1)
            ]
            + [f"Stay: {s.name} in {s.city}" for s in it.stays[:4]]
        )
        try:
            return await lite.edit(plan, text)
        except Exception:
            log.exception("edit parse failed; answering as a question")
            return Edit()

    # --- voice --------------------------------------------------------------------------

    async def hear(self, t: Turn, audio: Audio) -> str | None:
        """The words of a voice note, shown back as a heard event; None when there are none."""
        try:
            data = base64.b64decode(audio.data, validate=True)
        except (binascii.Error, ValueError):
            await self.say(t, BAD_AUDIO)
            return None
        lite = self.lite or get_lite()
        try:
            words = (await lite.transcribe(data, audio.mime)).strip()
        except Exception:
            log.exception("transcription failed")
            await self.say(t, HEARING_FAILED)
            return None
        if not words:
            await self.say(t, NOT_HEARD)
            return None
        log.info("route: voice note, %d characters heard", len(words))
        await t.emit(ChatEvent(type="heard", text=_cap(words, 2000)))
        return words[:4000]

    # --- trips --------------------------------------------------------------------------

    async def trip(self, t: Turn, texts: list[str]) -> None:
        c = t.conv
        noted = False

        async def progress(event: PlanEvent) -> None:
            nonlocal noted
            # Only once the planner is past intake: a reply that is only questions gets no note.
            if not noted and event.stage not in (PlanStage.intake, PlanStage.needs_input):
                noted = True
                await self.note(t, PLANNING)

        try:
            result = await self.api.plan("\n".join(texts), c.lang, progress)
        except ApiError as e:
            log.warning("plan failed: HTTP %s", e.status)
            # The draft is kept as it was: the user can just send their answer again.
            msg = PLAN_FAILED.format(why=e.detail) if 400 <= e.status < 500 else BUSY
            return await self.say(t, msg)
        if isinstance(result, Ask):
            c.draft, c.draft_at = texts[-8:], self.clock()
            known, keep = so_far(result.draft)
            named = [n for x in texts for n in rules.destinations(x)]
            c.draft_names = list(dict.fromkeys([*keep, *named]))
            lines = [ASKING, *(f"- {q}" for q in result.questions)]
            return await self.say(t, "\n".join(([known] if known else []) + lines), keep=keep)
        c.draft, c.draft_names = [], []
        await self.planned(t, result)

    async def planned(self, t: Turn, p: Planned, changed: str = "") -> None:
        c = t.conv
        c.itinerary, c.plan_id, c.share_token = p.itinerary, p.plan_id, p.share_token
        if p.plan_id and p.plan_id not in c.plan_ids:
            c.plan_ids.append(p.plan_id)
        t.plan_changed = True
        await t.emit(
            ChatEvent(
                type="plan",
                plan_id=p.plan_id,
                share_token=p.share_token,
                itinerary=p.itinerary,
                plan_changed=True,
            )
        )
        hint, chips = next_hint(p.itinerary)
        body = (changed + "\n\n" if changed else "") + summarise(p.itinerary) + "\n\n" + hint
        await self.say(
            t, body, keep=names(p.itinerary) + chips, tail=season_sources(p.itinerary), chips=chips
        )

    async def adopt(self, c: Conversation, plan_id: str, token: str | None) -> None:
        """The web page shows another plan: chat edits apply to that one from now on."""
        saved = await self.api.saved(plan_id)
        if saved is None and token:
            it = await self.api.shared(token)
            saved = (it, token) if it is not None else None
        if saved is not None:
            c.itinerary, c.share_token = saved
            c.plan_id = plan_id
            if plan_id not in c.plan_ids:
                c.plan_ids.append(plan_id)

    async def edit(self, t: Turn, intent: str, f: dict) -> None:
        c = t.conv
        it = c.itinerary
        if intent == "share":
            if not c.share_token:
                return await self.say(t, "Sharing needs a saved plan; plan your trip again first.")
            web = os.environ.get("SHARE_BASE_URL", "").rstrip("/")
            # The web's read-only page (TY4); without it, the API's JSON for the same plan.
            link = f"{web}/t/{c.share_token}/" if web else f"{self.api.base}/trips/{c.share_token}"
            return await self.say(t, "Your plan:", tail=link)
        days = it.days
        body: dict = {"intent": intent, "lang": c.lang.value}
        said = {"day": f.get("day"), "place": f.get("place"), "city": f.get("city")}
        n = f.get("day")
        if n is not None and not 1 <= n <= len(days):
            return await self.say(t, f"Your plan has days 1 to {len(days)}. {WHICH_DAY}")
        if intent in ("lighter_day", "move_stop") and n is None:
            return await self.say(t, WHICH_DAY)
        if n is not None:
            body["day"] = days[n - 1].date.isoformat()
        if intent == "move_day":
            cities = it.request.destinations
            want = f.get("city") or ""
            found = [x for x in cities if want and rules.same_place(want, [x])]
            if not found:
                msg = NOT_A_CITY.format(what=want, cities=", ".join(cities))
                return await self.say(t, msg, keep=[want, *cities])
            body["city"] = said["city"] = found[0]
        if intent in ("swap_stop", "remove_stop", "move_stop"):
            pool = (
                days[n - 1].stops
                if n is not None and intent != "move_stop"
                else [p for d in days for p in d.stops]
            )
            want = (f.get("place") or "").casefold()
            match = [p for p in pool if want and (want in p.name.casefold())]
            if not match:
                stops = ", ".join(p.name for p in pool)
                msg = NOT_FOUND.format(what=f.get("place") or "that", stops=stops)
                return await self.say(t, msg, keep=[f.get("place") or "", *(p.name for p in pool)])
            body["place_id"] = match[0].id
            said["place"] = match[0].name
        if intent == "add_stop":
            body["place"] = (f.get("place") or "")[:200]
        if intent == "transport":
            body["mode"] = f["mode"]
        if intent == "budget_style":
            body["style"] = f["style"]
        if intent == "change_stay":
            body["stay_pick"] = f.get("stay_pick") or "cheaper"
            if f.get("city"):
                body["city"] = f["city"]
        if intent == "rest_of_day":
            now = datetime.now(IST).replace(tzinfo=None, microsecond=0)
            body["now"] = (now + timedelta(minutes=f.get("minutes") or 0)).isoformat()
            if c.lat is not None and self.clock() - c.located_at < LOCATION_SECONDS:
                body["lat"], body["lng"] = c.lat, c.lng
        if intent == "booked":
            if not f.get("booked"):
                return await self.say(
                    t,
                    "Tell me the train or flight number and its times, for example: "
                    "booked train 17309 Bengaluru to Madgaon, 11 Dec 21:00 to 12 Dec 11:00",
                )
            body["booked"] = f["booked"]
        await self.note(t, REVISING)
        try:
            p = await self.api.revise(c.plan_id, body)
        except ApiError as e:
            if e.status == 404:
                c.itinerary = c.plan_id = c.share_token = None
                return await self.say(t, EXPIRED)
            return await self.say(t, e.detail if 400 <= e.status < 500 else BUSY)
        mode = MODE_WORDS.get(f.get("mode") or "", f.get("mode") or "")
        fallback = CHANGED[intent].format(
            day=said["day"], place=said["place"], city=said["city"], mode=mode, style=f.get("style")
        )
        await self.planned(t, p, changed=p.what or fallback)

    # --- guide and story ----------------------------------------------------------------

    async def guide(self, t: Turn, question: str) -> None:
        c = t.conv
        located = c.lat is not None and self.clock() - c.located_at < LOCATION_SECONDS
        q = GuideQuestion(
            question=question[:500],
            lang=c.lang,
            lat=c.lat if located else None,
            lng=c.lng if located else None,
        )
        log.info("route: guide (%d characters, lang %s)", len(question), c.lang.value)
        try:
            answer = await self.api.ask(q)
        except ApiError as e:
            log.warning("guide failed: HTTP %s", e.status)
            return await self.say(t, BUSY)
        await self.say(t, answer.text, tail=sources(answer))

    async def story(self, t: Turn, what: str, minutes: int, lang: Lang | None) -> None:
        """Katha of a place (or else a city): text in the user's language, audio when it matches."""
        c = t.conv
        if lang is not None:
            c.lang = lang
        await self.note(t, FINDING_STORY)
        told, err = None, ApiError(404, "no story")
        for kind in ("place", "city"):
            req = KathaRequest(subject_kind=kind, subject=what[:200], length_min=minutes, lang=c.lang)
            try:
                told = await self.api.katha(req)
                break
            except ApiError as e:
                err = e
                log.warning("katha as %s: HTTP %s", kind, e.status)
                if e.status != 404:
                    break
        if told is None:
            if err.status == 404:
                return await self.say(t, NO_STORY.format(what=what), keep=[what])
            return await self.say(t, STORY_BUSY)
        tail = "\n".join(f"[{i}] {src}" for i, src in enumerate(told.sources, 1))
        if told.lang == c.lang:
            body = _cap(told.text, MAX_TOTAL - len(tail) - 2) + "\n\n" + tail if tail else told.text
            await t.emit(ChatEvent(type="text", text=_cap(body)))
            for a in sorted(told.audio, key=lambda a: a.chapter):
                await t.emit(ChatEvent(type="audio", url=a.url, text=told.subject))
        else:
            await self.say(t, told.text, keep=[told.subject], tail=tail)

    # --- delete my data -----------------------------------------------------------------

    async def forget(self, t: Turn, lang: Lang) -> None:
        """Drop the conversation and delete the plans made through it."""
        ids = list(dict.fromkeys(t.conv.plan_ids))
        deleted = 0
        for plan_id in ids:
            deleted += await self.api.delete_plan(plan_id)
        if ids:
            english = FORGOTTEN.format(n=f"{deleted} of {len(ids)} saved plans")
        else:
            english = FORGOTTEN_NONE
        if deleted < len(ids) or not ids:
            english += " " + FORGOTTEN_KEPT
        t.conv = Conversation(lang=lang)
        t.forgotten = True
        await self.say(t, english, keep=[CONTACT])


def from_model(e: Edit) -> tuple[str, dict]:
    """Flash-Lite's Edit as the keyword rules' (intent, fields)."""
    f: dict = {
        "day": e.to_day if e.intent == "move_stop" else e.day,
        "place": e.place,
        "city": e.city,
        "mode": e.mode,
        "style": e.style,
        "stay_pick": e.stay_pick,
        "minutes": e.minutes,
    }
    if e.intent == "transport" and not e.mode:
        return "none", {}
    if e.intent == "budget_style" and not e.style:
        f["style"] = "comfort"
    if e.intent == "booked" and e.ref and e.depart and e.arrive and e.from_city and e.to_city:
        f["booked"] = {
            "mode": e.mode or "rail",
            "ref": e.ref[:20],
            "from": e.from_city,
            "to": e.to_city,
            "depart": e.depart,
            "arrive": e.arrive,
        }
    return e.intent, f


_locks: dict[str, asyncio.Lock] = {}


def _lock(cid: str) -> asyncio.Lock:
    """One message at a time per caller in this instance, so two quick messages don't race."""
    if len(_locks) > 5000:
        for k in [k for k, v in _locks.items() if not v.locked()]:
            del _locks[k]
    return _locks.setdefault(cid, asyncio.Lock())
