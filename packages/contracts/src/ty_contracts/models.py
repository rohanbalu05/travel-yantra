"""Travel Yantra shared contracts. Additive changes only without HQ approval."""

from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Lang(StrEnum):
    en = "en"
    hi = "hi"
    kn = "kn"
    ta = "ta"
    te = "te"
    bn = "bn"


class Pace(StrEnum):
    relaxed = "relaxed"
    balanced = "balanced"
    packed = "packed"


class Mode(StrEnum):
    road = "road"
    rail = "rail"
    air = "air"


class Traveller(_Model):
    name: str
    age: int = Field(ge=0, le=120)


class Constraints(_Model):
    budget_inr: int | None = Field(default=None, ge=0)
    pace: Pace = Pace.balanced
    mobility_needs: list[str] = Field(default_factory=list)
    dietary: list[str] = Field(default_factory=list)
    max_travel_hours_per_day: float = Field(default=8, gt=0, le=24)
    travellers: list[Traveller] = Field(default_factory=list)


class TripRequest(_Model):
    origin: str
    destinations: list[str] = Field(min_length=1)
    start_date: date
    end_date: date
    constraints: Constraints = Field(default_factory=Constraints)
    lang: Lang = Lang.en
    notes: str | None = None

    @model_validator(mode="after")
    def _dates_in_order(self) -> TripRequest:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class OpeningHours(_Model):
    day: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    opens: time
    closes: time


class Place(_Model):
    id: str
    name: str
    native_names: dict[Lang, str] = Field(default_factory=dict)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    category: str
    opening_hours: list[OpeningHours] = Field(default_factory=list)
    typical_visit_minutes: int = Field(ge=0)
    source: str


class Leg(_Model):
    from_: str = Field(alias="from")
    to: str
    mode: Mode
    depart: datetime
    arrive: datetime
    minutes: int = Field(ge=0)
    cost_inr: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _times_in_order(self) -> Leg:
        if self.arrive < self.depart:
            raise ValueError("arrive must not be before depart")
        return self


class SellerOffer(_Model):
    seller: str
    price_inr: int | None = Field(default=None, ge=0)
    currency: str = "INR"
    url: str
    kind: Literal["deep_link", "check_price"]
    fetched_at: datetime


class TransportOption(_Model):
    mode: Mode
    legs: list[Leg] = Field(min_length=1)
    total_minutes: int = Field(ge=0)
    total_cost_inr: int = Field(ge=0)
    comfort: int = Field(ge=1, le=5)
    offers: list[SellerOffer] = Field(default_factory=list)


class Stay(_Model):
    name: str
    city: str
    check_in: date
    check_out: date
    price_per_night_inr: int = Field(ge=0)
    offers: list[SellerOffer] = Field(default_factory=list)

    @model_validator(mode="after")
    def _dates_in_order(self) -> Stay:
        if self.check_out < self.check_in:
            raise ValueError("check_out must not be before check_in")
        return self


class DayPlan(_Model):
    date: date
    stops: list[Place] = Field(default_factory=list)
    legs: list[Leg] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BudgetSummary(_Model):
    transport_inr: int = Field(ge=0)
    stay_inr: int = Field(ge=0)
    activities_inr: int = Field(default=0, ge=0)
    food_inr: int = Field(default=0, ge=0)
    total_inr: int = Field(ge=0)
    within_budget: bool | None = None


class Itinerary(_Model):
    request: TripRequest
    days: list[DayPlan]
    transport: list[TransportOption] = Field(default_factory=list)
    stays: list[Stay] = Field(default_factory=list)
    budget: BudgetSummary
    warnings: list[str] = Field(default_factory=list)
    lang: Lang = Lang.en


class StorySegment(_Model):
    label: Literal["legend", "history"]
    text: str


class KathaStory(_Model):
    subject_kind: Literal["place", "city", "day"]
    subject: str
    length_min: Literal[2, 5, 10]
    text: str
    segments: list[StorySegment] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    lang: Lang = Lang.en


class Citation(_Model):
    title: str
    url: str | None = None


class GuideAnswer(_Model):
    text: str
    citations: list[Citation] = Field(default_factory=list)
    emergency_places: list[Place] = Field(default_factory=list)
    lang: Lang = Lang.en


class GuideQuestion(_Model):
    """Body of POST /guide/ask."""

    question: str = Field(min_length=1, max_length=500)
    lang: Lang = Lang.en
    city: str | None = None
    # The current stop as in the itinerary: its name, and its Place.id when known.
    place_name: str | None = None
    place_id: str | None = None
    # The traveller's position, used for emergency questions.
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    has_elderly: bool = False


class PlanStage(StrEnum):
    intake = "intake"
    planning = "planning"
    solving = "solving"
    checking = "checking"
    repairing = "repairing"
    narrating = "narrating"
    needs_input = "needs_input"
    done = "done"
    error = "error"


class PlanStep(StrEnum):
    """Which agent finished. Several steps share one stage (the four planners are all `planning`)."""

    intake = "intake"
    transport = "transport"
    places = "places"
    stays = "stays"
    story = "story"
    solver = "solver"
    checker = "checker"
    repair = "repair"
    narrator = "narrator"


class ViolationCode(StrEnum):
    over_budget = "over_budget"
    closed = "closed"
    long_day = "long_day"
    too_much_travel = "too_much_travel"
    no_rest = "no_rest"


class Violation(_Model):
    code: ViolationCode
    message: str
    day: date | None = None
    place_id: str | None = None


class PlanText(_Model):
    """Free-text body for POST /plan; intake turns it into a TripRequest or asks questions."""

    text: str = Field(min_length=1, max_length=4000)
    lang: Lang = Lang.en


class PlanEvent(_Model):
    """One Server-Sent Event of POST /plan. The stream ends after the first done, needs_input or error."""

    stage: PlanStage
    message: str
    # Only sent once a complete Itinerary (request, days, budget) exists; earlier stages send None.
    partial: Itinerary | None = None
    step: PlanStep | None = None
    # Intake follow-ups (at most 3), only on needs_input.
    questions: list[str] = Field(default_factory=list, max_length=3)
    # On checking events: what the checker found this round.
    violations: list[Violation] = Field(default_factory=list)
    # Repair round 1..3 on checking and repairing events.
    iteration: int | None = Field(default=None, ge=1, le=3)
    # On error: whether trying again may help.
    retryable: bool = False
    # On done: opaque id for POST /plan/{plan_id}/revise.
    plan_id: str | None = None
