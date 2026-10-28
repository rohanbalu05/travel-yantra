"""Intake: free text (English, Hinglish or a filled form) becomes a TripRequest, or up to 3 questions.

The model only fills a flat draft; code decides what is missing and builds the TripRequest.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel, Field, ValidationError

from ty_contracts import (
    BudgetStyle,
    Constraints,
    Lang,
    Mode,
    Pace,
    PlanText,
    Traveller,
    TripRequest,
)

from .llm import Model

MAX_QUESTIONS = 3
IST = timezone(timedelta(hours=5, minutes=30))
# One question per missing detail, asked once, in this order. Hindi has its own wording; other languages
# get English until their translations are reviewed.
ASK = {
    "origin": "Where will you start from?",
    "destinations": "Where would you like to go?",
    "dates": "Which dates are you travelling (first and last day)?",
    "length": "How many days is the trip?",
    "travellers": "How many of you are travelling, and is anyone a child or over 60?",
}
ASK_HI = {
    "origin": "आप कहाँ से यात्रा शुरू करेंगे?",
    "destinations": "आप कहाँ जाना चाहेंगे?",
    "dates": "आप किन तारीखों में यात्रा कर रहे हैं (पहला और आखिरी दिन)?",
    "length": "यात्रा कितने दिनों की है?",
    "travellers": "आप कितने लोग जा रहे हैं, और क्या कोई बच्चा या 60 साल से ऊपर का है?",
}


def ask(field: str, lang: Lang) -> str:
    return (ASK_HI if lang is Lang.hi else ASK)[field]


class DraftTraveller(BaseModel):
    name: str
    age: int


class IntakeDraft(BaseModel):
    """What the model extracts. Every field is optional so the model never has to invent one."""

    origin: str | None = None
    destinations: list[str] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    budget_inr: int | None = None
    pace: Pace | None = None
    max_travel_hours_per_day: float | None = None
    travellers: list[DraftTraveller] = Field(default_factory=list)
    mobility_needs: list[str] = Field(default_factory=list)
    dietary: list[str] = Field(default_factory=list)
    # "a 3-day trip" (days) or "4 nights" (nights + 1): the end date from the start date.
    days: int | None = None
    transport_mode: Mode | None = None
    budget_style: BudgetStyle | None = None
    # Kept for older cached drafts; never shown (our own wording asks for each missing field once).
    questions: list[str] = Field(default_factory=list)


class IntakeResult(BaseModel):
    request: TripRequest | None = None
    questions: list[str] = Field(default_factory=list)
    # What was understood so far, for a pre-filled form when questions remain.
    draft: IntakeDraft | None = None


def prompt(text: str, today: date) -> str:
    return (
        "You turn an Indian traveller's message into trip fields. The message may be English, Hinglish "
        "(Hindi in Latin script) or another Indian language.\n"
        f"Today is {today.isoformat()}. Resolve dates to YYYY-MM-DD; a date without a year is the next one "
        "after today. Days: the trip's length in days when they say it ('a 3-day trip' is 3; '4 nights' is 5); "
        "leave end_date empty unless they give the last day.\n"
        "Use English place names (Bengaluru, Mysuru, Goa). Leave a field empty when the message does not say it; "
        "never guess origin or dates. Budget is the total in rupees (1 lakh = 100000). Pace: relaxed when they "
        "mention elders, kids or taking it easy; packed when they want to see a lot; else leave it empty. "
        "Travellers: only when the message says who is going. Then list every person going, including the "
        "writer (name 'You') unless they say they are not going; 'with my parents and sister' is 4 people, "
        "'me and my wife' is 2, 'solo' is 1. Use a role as the name when no name is given. When an age is not "
        "stated, estimate it from the role: parents of an adult 60, grandparents 75, a child 8, a spouse, "
        "sibling or friend 30. 'Just me' or 'solo' is 1; 'a couple' is 2. A message that does not say who is "
        "going has no travellers. A day trip is 1 day.\n"
        "transport_mode: rail, road or air only when they state a preference (train; car, bus or drive; "
        "flight); empty when they do not say or are not sure. budget_style: shoestring (cheap, backpacking, "
        "low budget), comfort, or luxury, only when they say so.\n\n"
        f"Message:\n{text}"
    )


_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "do": 2, "teen": 3, "char": 4}
_N = r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)"
_SOLO = re.compile(r"\b(just me|only me|solo|alone|by myself|on my own|akela|akeli|single traveller)\b")
_COUPLE = re.compile(r"\b(couple|honeymoon|my (wife|husband|partner)|me and my (wife|husband|partner|girlfriend|boyfriend)"
                     r"|two of us|both of us|hum do|do log)\b")
_FRIENDS = re.compile(rf"\bwith {_N} (friends|others|colleagues)\b")
_COUNT = re.compile(rf"\b{_N} (people|persons|adults|of us|travellers|travelers|friends|pax|log|members)\b")
_MY_AGE = re.compile(r"\b(?:i am|i'm|im|aged|age)\s+(\d{1,2})\b")
_BOTH_AGE = re.compile(r"\b(?:both|all|each)\s+(?:are\s+|aged\s+)?(\d{1,2})\b")


def party_from_text(text: str) -> list[DraftTraveller]:
    """How many go, from plain words ("just me", "a couple", "two adults", "with 3 friends"), with the ages
    stated ("I am 20", "both 38"); 30 when not stated. Empty when the text does not say. The model's list
    wins when it has one; this keeps a stated count from being asked again."""
    t = normalise(text)
    count = 0
    if m := _FRIENDS.search(t):
        count = int(_NUM.get(m.group(1), m.group(1))) + 1
    elif m := _COUNT.search(t):
        count = int(_NUM.get(m.group(1), m.group(1)))
    elif _COUPLE.search(t):
        count = 2
    elif _SOLO.search(t):
        count = 1
    if not 1 <= count <= 20:
        return []
    ages = [30] * count
    if m := _BOTH_AGE.search(t):
        ages = [int(m.group(1))] * count
    if m := _MY_AGE.search(t):
        ages[0] = int(m.group(1))
    return [DraftTraveller(name="You" if i == 0 else f"Traveller {i + 1}", age=a) for i, a in enumerate(ages)]


_DAYS = re.compile(rf"\b{_N}[ -]days?\b")


def days_from_text(text: str) -> int | None:
    """The trip's length in days from plain words: "a day trip" is 1, "5 days" or "3-day" is that many."""
    t = normalise(text)
    if m := _DAYS.search(t):
        return int(_NUM.get(m.group(1), m.group(1)))
    return 1 if re.search(r"\bday trip\b", t) else None


def to_request(draft: IntakeDraft, lang: Lang, notes: str | None = None) -> IntakeResult:
    if not draft.travellers and notes and (party := party_from_text(notes)):
        draft = draft.model_copy(update={"travellers": party})
    if draft.start_date and not draft.end_date and not draft.days and notes and (n := days_from_text(notes)):
        draft = draft.model_copy(update={"days": n})
    if draft.start_date and not draft.end_date and draft.days and 0 < draft.days <= 60:
        draft = draft.model_copy(update={"end_date": draft.start_date + timedelta(days=draft.days - 1)})
    missing = []
    if not draft.origin:
        missing.append("origin")
    if not draft.destinations:
        missing.append("destinations")
    if not draft.start_date:
        missing.append("dates")
    elif not draft.end_date:
        missing.append("length")
    if not draft.travellers:
        missing.append("travellers")  # never assume one traveller
    if missing:
        # One question per missing field, in our own wording (the model's would repeat them in other words).
        return IntakeResult(questions=[ask(m, lang) for m in missing][:MAX_QUESTIONS], draft=draft)
    c = Constraints(
        budget_inr=draft.budget_inr,
        pace=draft.pace or Pace.balanced,
        mobility_needs=draft.mobility_needs,
        dietary=draft.dietary,
        travellers=[Traveller(name=t.name, age=t.age) for t in draft.travellers if 0 <= t.age <= 120],
        budget_style=draft.budget_style,
        **({"max_travel_hours_per_day": draft.max_travel_hours_per_day}
           if draft.max_travel_hours_per_day and 0 < draft.max_travel_hours_per_day <= 24 else {}),
    )
    try:
        request = TripRequest(origin=draft.origin, destinations=draft.destinations, start_date=draft.start_date,
                              end_date=draft.end_date, constraints=c, lang=lang, notes=notes,
                              transport_mode=draft.transport_mode)
    except ValidationError:
        return IntakeResult(questions=[ask("dates", lang)], draft=draft)
    return IntakeResult(request=request, draft=draft)


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip(" .!?")


# Model results by (normalised text, lang, today). Small and per process; a repeat costs no model call.
_cache: OrderedDict[tuple[str, Lang, date], IntakeResult] = OrderedDict()
CACHE_SIZE = 512

MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
# A 3-letter month or the full name ("sept" too); never a word that merely starts like one ("decide").
_MON = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?"
        r"|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b")
# "11-14 dec", "11 to 14 dec 2026", "31 oct se 1 nov"
_DATES = re.compile(rf"(\d{{1,2}})(?:\s+{_MON})?\s*(?:-|–|to|se|till|until)\s*(\d{{1,2}})\s+{_MON}(?:\s+(\d{{4}}))?")
# "bengaluru to goa", "from bengaluru to mysuru", "bangalore se mysore"
_ROUTE = re.compile(r"(?:from\s+)?([a-z][a-z]*(?: [a-z]+)?)\s+(?:to|se|->|→)\s+([a-z][a-z]*(?: [a-z]+)?)")
# Words that may stay unparsed in a quick-path message ("Bengaluru to Goa, 11-14 Dec trip").
_FILLER = {"trip", "plan", "a", "for", "on", "jaana", "hai", "please", "travel", "going", "from", "and", "-"}
# "for 2", "4 people", "2 adults", "solo": how many go (all adults; ages unknown, so 30).
_PARTY = re.compile(r"\b(?:for\s+(\d{1,2})(?:\s+(?:people|persons|adults|of us|pax))?|(\d{1,2})\s+(?:people|persons|adults|pax)"
                    r"|(solo|alone|just me))\b")


def _city(name: str) -> str | None:
    """A city the planner knows (TY2's corpus names, or a sample city), else None."""
    from guide.planner import corpus_city

    from .fakes import BY_CITY

    name = name.strip()
    return corpus_city(name) or (name.title() if name.lower() in BY_CITY else None)


def _on_or_after(day: int, month: int, year: int | None, today: date) -> date | None:
    try:
        d = date(year or today.year, month, day)
    except ValueError:
        return None
    return d.replace(year=d.year + 1) if year is None and d < today else d


def quick_parse(text: str, lang: Lang, today: date) -> IntakeResult | None:
    """A form-like message ("Bengaluru to Goa, 11-14 Dec", or Hinglish "se") needs no model. Anything more
    (travellers, budget, pace, unknown cities, extra words) returns None and goes to the model."""
    t = normalise(text)
    party = _PARTY.search(t)
    count = (1 if party.group(3) else int(party.group(1) or party.group(2))) if party else 0
    if party:
        t = (t[:party.start()] + " " + t[party.end():]).strip()
    if party and not 1 <= count <= 20:
        return None
    dates = _DATES.search(t)
    route = _ROUTE.search(t[:dates.start()] if dates else t)
    if not route or not dates:
        return None
    origin, dest = _city(route.group(1)), _city(route.group(2))
    d1, m1, d2, m2, year = dates.groups()
    end = _on_or_after(int(d2), MONTHS[m2[:3]], int(year) if year else None, today)
    start = _on_or_after(int(d1), MONTHS[(m1 or m2)[:3]], end.year if end else None, today) if end else None
    if start and end and start > end:  # "28 dec - 2 jan": the start is in the year before the end
        start = start.replace(year=start.year - 1)
    rest = (t[:route.start()] + " " + t[route.end():dates.start()] + " " + t[dates.end():]).replace(",", " ")
    if not (origin and dest and start and end) or set(rest.split()) - _FILLER:
        return None
    if not count and (said := party_from_text(text)):
        count = len(said)
    travellers = [DraftTraveller(name="You" if i == 0 else f"Traveller {i + 1}", age=30) for i in range(count)]
    draft = IntakeDraft(origin=origin, destinations=[dest], start_date=start, end_date=end, travellers=travellers)
    return to_request(draft, lang, notes=text[:500])


async def intake(body: TripRequest | PlanText, model: Model, today: date | None = None) -> IntakeResult:
    """A form (TripRequest) passes straight through. Free text: the quick parser, then the cache, then the
    model (Flash-Lite)."""
    if isinstance(body, TripRequest):
        return IntakeResult(request=body)
    today = today or datetime.now(IST).date()
    quick = quick_parse(body.text, body.lang, today)
    if quick:
        return quick
    key = (normalise(body.text), body.lang, today)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key].model_copy(deep=True)
    draft = await model.json(prompt(body.text, today), IntakeDraft, tier="lite", thinking="minimal", label="intake")
    result = to_request(draft, body.lang, notes=body.text[:500])
    _cache[key] = result
    while len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return result.model_copy(deep=True)
