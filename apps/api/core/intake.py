"""Intake: free text (English, Hinglish or a filled form) becomes a TripRequest, or up to 3 questions.

The model only fills a flat draft; code decides what is missing and builds the TripRequest.
"""

from __future__ import annotations

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


def prompt(text: str, today: date) -> str:
    return (
        "You turn an Indian traveller's message into trip fields. The message may be English, Hinglish "
        "(Hindi in Latin script) or another Indian language.\n"
        f"Today is {today.isoformat()}. Resolve dates to YYYY-MM-DD; a date without a year is the next one "
        "after today. A single date with N nights ends N days later.\n"
        "Use English place names (Bengaluru, Mysuru, Goa). Leave a field empty when the message does not say it; "
        "never guess origin or dates. Budget is the total in rupees (1 lakh = 100000). Pace: relaxed when they "
        "mention elders, kids or taking it easy; packed when they want to see a lot; else leave it empty. "
        "For each traveller with a known age, add {name, age}; use a role as the name when no name is given.\n"
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


async def intake(body: TripRequest | PlanText, model: Model, today: date | None = None) -> IntakeResult:
    """A form (TripRequest) passes straight through; free text goes to the model (Flash-Lite)."""
    if isinstance(body, TripRequest):
        return IntakeResult(request=body)
    draft = await model.json(prompt(body.text, today or datetime.now(IST).date()), IntakeDraft, tier="lite", thinking="minimal")
    # Model questions are dropped here unless something is missing; they never reach a complete request.
    return to_request(draft, body.lang, notes=body.text[:500])
