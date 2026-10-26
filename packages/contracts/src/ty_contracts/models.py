"""Travel Yantra shared contracts. Additive changes only without HQ approval."""

from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class PlanStage(StrEnum):
    intake = "intake"
    planning = "planning"
    solving = "solving"
    checking = "checking"
    narrating = "narrating"
    done = "done"
    error = "error"


class PlanEvent(_Model):
    stage: PlanStage
    message: str
    partial: Itinerary | None = None
