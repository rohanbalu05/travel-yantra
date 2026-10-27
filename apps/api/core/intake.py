"""Intake: free text (English, Hinglish or a filled form) becomes a TripRequest, or up to 3 questions.

The model only fills a flat draft; code decides what is missing and builds the TripRequest.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel, Field, ValidationError

from ty_contracts import Constraints, Lang, Pace, PlanText, Traveller, TripRequest

from .llm import Model

MAX_QUESTIONS = 3
IST = timezone(timedelta(hours=5, minutes=30))
ASK = {
    "origin": "Where will you start from?",
    "destinations": "Where would you like to go?",
    "dates": "Which dates are you travelling (first and last day)?",
}


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
        "after today. A single date with N nights ends N days later.\n"
        "Use English place names (Bengaluru, Mysuru, Goa). Leave a field empty when the message does not say it; "
        "never guess origin or dates. Budget is the total in rupees (1 lakh = 100000). Pace: relaxed when they "
        "mention elders, kids or taking it easy; packed when they want to see a lot; else leave it empty. "
        "Travellers: list every person going, including the writer (name 'You') unless they say they are not "
        "going; 'with my parents and sister' is 4 people. Use a role as the name when no name is given. When an "
        "age is not stated, estimate it from the role: parents of an adult 60, grandparents 75, a child 8, "
        "a spouse, sibling or friend 30.\n"
        "In questions, list at most 3 short follow-up questions for missing origin, destination or dates only.\n\n"
        f"Message:\n{text}"
    )


def to_request(draft: IntakeDraft, lang: Lang, notes: str | None = None) -> IntakeResult:
    missing = []
    if not draft.origin:
        missing.append("origin")
    if not draft.destinations:
        missing.append("destinations")
    if not draft.start_date:
        missing.append("dates")
    if missing:
        # Our wording for each missing field; the model's own questions only fill spare slots.
        asks = [ASK[m] for m in missing]
        extra = [q for q in draft.questions if q not in asks]
        return IntakeResult(questions=(asks + extra)[:MAX_QUESTIONS])
    c = Constraints(
        budget_inr=draft.budget_inr,
        pace=draft.pace or Pace.balanced,
        mobility_needs=draft.mobility_needs,
        dietary=draft.dietary,
        travellers=[Traveller(name=t.name, age=t.age) for t in draft.travellers if 0 <= t.age <= 120],
        **({"max_travel_hours_per_day": draft.max_travel_hours_per_day}
           if draft.max_travel_hours_per_day and 0 < draft.max_travel_hours_per_day <= 24 else {}),
    )
    try:
        request = TripRequest(origin=draft.origin, destinations=draft.destinations, start_date=draft.start_date,
                              end_date=draft.end_date or draft.start_date, constraints=c, lang=lang, notes=notes)
    except ValidationError:
        return IntakeResult(questions=[ASK["dates"]])
    return IntakeResult(request=request)


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
    return IntakeResult(request=TripRequest(origin=origin, destinations=[dest], start_date=start, end_date=end,
                                            lang=lang, notes=text[:500]))


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
    draft = await model.json(prompt(body.text, today), IntakeDraft, tier="lite", thinking="minimal")
    # Model questions are dropped here unless something is missing; they never reach a complete request.
    result = to_request(draft, body.lang, notes=body.text[:500])
    result.draft = draft
    _cache[key] = result
    while len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return result.model_copy(deep=True)
