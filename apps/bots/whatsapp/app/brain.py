"""Turn one chat message into one reply: plan a trip, or ask the guide."""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

import httpx
from ty_contracts import GuideAnswer, Itinerary, Lang, PlanEvent, PlanStage, TripRequest

SAMPLE = Path(__file__).parent / "samples/goa_family.json"
MAX_REPLY = 4000  # WhatsApp text bodies are capped at 4096 characters

HELP = (
    "Namaste! Tell me your trip like this:\n"
    "Bengaluru to Goa, 11-14 Dec\n"
    "or ask me anything about a place, its food or its history."
)
VOICE = (
    "Sorry, I can only read text messages for now. "
    "Please type your question and I will reply right away."
)
NOT_TEXT = "Sorry, I can only read text messages for now. Please type your message."

# Unicode blocks of the Indic scripts we support; Hinglish (Latin script) counts as English.
SCRIPTS = {
    Lang.hi: (0x0900, 0x097F),
    Lang.bn: (0x0980, 0x09FF),
    Lang.ta: (0x0B80, 0x0BFF),
    Lang.te: (0x0C00, 0x0C7F),
    Lang.kn: (0x0C80, 0x0CFF),
}

MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_PLACE = r"[A-Za-z][A-Za-z .]*?"
# "Bengaluru to Goa", "Bengaluru se Goa" (Hinglish), "from Bengaluru to Goa"
ROUTE = re.compile(
    rf"(?:from\s+)?(?P<origin>{_PLACE})\s+(?:to|se)\s+(?P<dest>{_PLACE})(?=[,\s]|$)", re.IGNORECASE
)
# "11-14 Dec", "11 to 14 dec", "11 dec - 14 dec", "11 Dec se 14 Dec"
DATES = re.compile(
    rf"(?P<d1>\d{{1,2}})\s*(?P<m1>{_MONTH})?\s*(?:-|–|to|se|till|tak)\s*"
    rf"(?P<d2>\d{{1,2}})\s*(?P<m2>{_MONTH})\b",
    re.IGNORECASE,
)
FILLER = re.compile(r"^(?:plan|trip|a|my|i want|want|mujhe|hume|chalo|jaana hai)\s+", re.IGNORECASE)


def detect_lang(text: str) -> Lang:
    counts = {lang: 0 for lang in SCRIPTS}
    for ch in text:
        for lang, (lo, hi) in SCRIPTS.items():
            if lo <= ord(ch) <= hi:
                counts[lang] += 1
    lang, n = max(counts.items(), key=lambda kv: kv[1])
    return lang if n else Lang.en


def _clean(place: str) -> str:
    place = place.strip(" .")
    while (m := FILLER.match(place)) is not None:
        place = place[m.end() :]
    return place.strip().title()


def parse_trip(text: str, today: date) -> TripRequest | None:
    """Read 'Origin to Destination, d1-d2 Mon' (English or Hinglish); None if it isn't a trip."""
    route, dates = ROUTE.search(text), DATES.search(text)
    if not route or not dates:
        return None
    m2 = MONTHS[dates["m2"].lower()]
    m1 = MONTHS[dates["m1"].lower()] if dates["m1"] else m2
    year = today.year
    try:
        start = date(year, m1, int(dates["d1"]))
        if start < today:
            year += 1
            start = start.replace(year=year)
        end = date(year if m2 >= m1 else year + 1, m2, int(dates["d2"]))
    except ValueError:
        return None
    if end < start:
        return None
    origin, dest = _clean(route["origin"]), _clean(route["dest"])
    if not origin or not dest:
        return None
    return TripRequest(origin=origin, destinations=[dest], start_date=start, end_date=end)


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
    return _cap("\n".join(lines))


def _cap(text: str) -> str:
    return text if len(text) <= MAX_REPLY else text[: MAX_REPLY - 1] + "…"


class Brain:
    """Calls the API at API_BASE_URL; without it, answers from the Goa sample."""

    def __init__(self, base: str | None = None, today: date | None = None):
        base = base if base is not None else os.environ.get("API_BASE_URL", "")
        self.base = base.rstrip("/")
        self.today = today

    async def reply(self, text: str) -> str:
        text = text.strip()
        if not text or text.lower() in {"hi", "hello", "help", "namaste", "start"}:
            return HELP
        lang = detect_lang(text)
        trip = parse_trip(text, self.today or date.today())
        if trip is not None:
            trip = trip.model_copy(update={"lang": lang})
            return summarise(await self.plan(trip))
        answer = await self.ask(text, lang)
        cites = "\n".join(f"- {c.title}" + (f" {c.url}" if c.url else "") for c in answer.citations)
        return _cap(answer.text + (f"\n\nSources:\n{cites}" if cites else ""))

    async def plan(self, trip: TripRequest) -> Itinerary:
        if not self.base:
            sample = json.loads(SAMPLE.read_text(encoding="utf-8"))["itinerary"]
            it = Itinerary.model_validate(sample)
            return it.model_copy(update={"warnings": [*it.warnings, "offline sample plan"]})
        final = None
        async with (
            httpx.AsyncClient(timeout=120) as client,
            client.stream(
                "POST", f"{self.base}/plan", json=json.loads(trip.model_dump_json())
            ) as r,
        ):
            r.raise_for_status()
            async for line in r.aiter_lines():
                # ponytail: assumes /plan streams SSE `data: <PlanEvent json>` lines
                if not line.startswith("data:"):
                    continue
                event = PlanEvent.model_validate_json(line[5:].strip())
                if event.stage == PlanStage.error:
                    raise RuntimeError(event.message)
                if event.partial is not None:
                    final = event.partial
                if event.stage == PlanStage.done:
                    break
        if final is None:
            raise RuntimeError("plan finished without an itinerary")
        return final

    async def ask(self, question: str, lang: Lang) -> GuideAnswer:
        if not self.base:
            return GuideAnswer(
                text=f"(offline sample) I would ask the guide: {question}", lang=lang
            )
        async with httpx.AsyncClient(timeout=60) as client:
            # ponytail: assumes POST /guide/ask takes {question, lang} (card #23)
            r = await client.post(
                f"{self.base}/guide/ask", json={"question": question, "lang": lang}
            )
            r.raise_for_status()
            return GuideAnswer.model_validate(r.json())
