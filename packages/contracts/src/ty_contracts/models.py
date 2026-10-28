"""Travel Yantra shared contracts. Additive changes only without HQ approval."""

from __future__ import annotations

import datetime as dt
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


class BudgetStyle(StrEnum):
    """How the traveller likes to spend: stay band, food per day, rail class, air or rail."""

    shoestring = "shoestring"
    comfort = "comfort"
    luxury = "luxury"


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
    # None plans as comfort.
    budget_style: BudgetStyle | None = None


class TripRequest(_Model):
    origin: str
    destinations: list[str] = Field(min_length=1)
    start_date: date
    end_date: date
    constraints: Constraints = Field(default_factory=Constraints)
    lang: Lang = Lang.en
    notes: str | None = None
    # Days in each destination, in order (multi-city). None shares the days out evenly.
    days_per_destination: list[int] | None = None
    # The traveller's chosen way to travel; every journey (out, between cities, home) prefers it. None: best ranked.
    transport_mode: Mode | None = None

    @model_validator(mode="after")
    def _dates_in_order(self) -> TripRequest:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if self.days_per_destination is not None:
            days = (self.end_date - self.start_date).days + 1
            if len(self.days_per_destination) != len(self.destinations) or sum(self.days_per_destination) != days:
                raise ValueError("days_per_destination needs one count per destination, adding up to the trip's days")
            if any(n < 0 for n in self.days_per_destination):
                raise ValueError("days_per_destination counts must not be negative")
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
    # The official ticket site only (TY2, from the corpus).
    ticket_url: str | None = None


class Leg(_Model):
    from_: str = Field(alias="from")
    to: str
    mode: Mode
    depart: datetime
    arrive: datetime
    minutes: int = Field(ge=0)
    cost_inr: int = Field(ge=0)
    # Set on a DayPlan's journeys: "outbound" (origin to the first city, opens day 1), "between" (city to
    # city, opens that city's first day), "home" (closes the last day), "transfer" (from the station or city
    # centre to the first stop, after a journey). None for stop-to-stop legs.
    role: Literal["outbound", "between", "home", "transfer"] | None = None
    # Train number (5 digits) for rail, flight number for air, when known.
    ref: str | None = None
    # A journey the traveller has booked (ReviseIntent.booked): kept as given; the days are planned around it.
    booked: bool = False

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
    # Set by TY1 on Itinerary.transport: the whole-trip total (BudgetSummary.total_inr) the plan would have
    # with this option, as the transport revise computes it. The option in use equals Itinerary.budget.total_inr.
    trip_total_inr: int | None = Field(default=None, ge=0)


RankBy = Literal["balanced", "time", "cost", "changes"]


class CompareRequest(_Model):
    """Body of POST /routes/compare (TY3)."""

    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    date: dt.date | None = None
    depart_time: dt.time = time(8, 0)
    rank_by: RankBy = "balanced"
    modes: list[Mode] = Field(default_factory=lambda: list(Mode), min_length=1)
    travellers: int = Field(default=1, ge=1, le=20)


class CityRef(_Model):
    name: str
    lat: float
    lng: float


class RankedOption(_Model):
    id: str
    rank: int = Field(ge=1)
    # Vehicle changes, first and last mile transfers included.
    changes: int = Field(ge=0)
    score: float = Field(ge=0)
    # Where the data came from: sample_rail | routes_api | haversine | fake_air | walk
    sources: list[str]
    option: TransportOption


class Unavailable(_Model):
    mode: Mode
    reason: str


class CompareResponse(_Model):
    origin: CityRef
    destination: CityRef
    date: dt.date
    rank_by: RankBy
    options: list[RankedOption]
    unavailable: list[Unavailable] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Stay(_Model):
    name: str
    city: str
    check_in: date
    check_out: date
    price_per_night_inr: int = Field(ge=0)
    offers: list[SellerOffer] = Field(default_factory=list)
    # Stable id for ReviseRequest.stay_id; stars, guest rating (out of 5) and review count when the source has them.
    id: str | None = None
    stars: int | None = Field(default=None, ge=1, le=5)
    rating: float | None = Field(default=None, ge=0, le=5)
    reviews: int | None = Field(default=None, ge=0)
    # "hotel" or "rental"; sample is True for illustrative stays that are not a real listing.
    kind: str | None = None
    sample: bool = False

    @model_validator(mode="after")
    def _dates_in_order(self) -> Stay:
        if self.check_out < self.check_in:
            raise ValueError("check_out must not be before check_in")
        return self


class StopTime(_Model):
    """When a stop is reached, its visit starts (after any wait for opening time) and ends."""

    place_id: str
    arrive: datetime
    start: datetime
    leave: datetime


class DayPlan(_Model):
    date: date
    stops: list[Place] = Field(default_factory=list)
    legs: list[Leg] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # A short heading, e.g. "Day 1 · Sat 31 Oct · Arrive in Mysuru".
    title: str | None = None
    # One entry per stop, in visiting order (the first stop included).
    schedule: list[StopTime] = Field(default_factory=list)


class BudgetSummary(_Model):
    transport_inr: int = Field(ge=0)
    stay_inr: int = Field(ge=0)
    activities_inr: int = Field(default=0, ge=0)
    food_inr: int = Field(default=0, ge=0)
    # Getting around in each city: transfers from the station and rides between stops (cabs for the party).
    local_transport_inr: int = Field(default=0, ge=0)
    total_inr: int = Field(ge=0)
    within_budget: bool | None = None
    # Food per person per day used for food_inr (a stated estimate for the budget style).
    food_per_person_day_inr: int | None = Field(default=None, ge=0)


class SeasonNote(_Model):
    """A sentence quoted from a source about the season at a destination (TY2's season scout)."""

    city: str
    text: str
    source_url: str
    # "month": the source names a month of the trip; "general": the destination's climate; "event": a dated
    # festival or event (TY2 keeps only those whose window overlaps the trip).
    kind: Literal["month", "general", "event"]


class Itinerary(_Model):
    request: TripRequest
    days: list[DayPlan]
    transport: list[TransportOption] = Field(default_factory=list)
    stays: list[Stay] = Field(default_factory=list)
    budget: BudgetSummary
    warnings: list[str] = Field(default_factory=list)
    lang: Lang = Lang.en
    # Quoted, sourced season notes for the trip's cities and months; empty when the sources say nothing.
    season_notes: list[SeasonNote] = Field(default_factory=list)
    # Why the plan travels the way it does when the traveller did not choose ("Flight: the train takes ...").
    transport_reason: str | None = None


class StorySegment(_Model):
    # "disputed": sources disagree; the text states both versions (design/katha-style.md rule 9).
    label: Literal["legend", "history", "disputed"]
    text: str


class KathaRequest(_Model):
    """Body of the Katha story endpoint (TY2)."""

    subject_kind: Literal["place", "city", "day"]
    subject: str = Field(min_length=1, max_length=200)
    length_min: Literal[2, 5, 10]
    lang: Lang = Lang.en
    # Day stories only: stop names or planner place ids, in visiting order.
    places: list[str] = Field(default_factory=list)


class KathaAudio(_Model):
    """One narrated chapter of a Katha story (TY2), played in chapter order."""

    chapter: int = Field(ge=1)  # 1-based; a 2-minute story has one
    url: str  # MP3 in TY6's bucket
    voice: str  # e.g. "hi-IN-Chirp3-HD-Kore"
    characters: int = Field(ge=0)  # what text-to-speech billed for this chapter


class KathaStory(_Model):
    subject_kind: Literal["place", "city", "day"]
    subject: str
    length_min: Literal[2, 5, 10]
    text: str
    segments: list[StorySegment] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    lang: Lang = Lang.en
    audio: list[KathaAudio] = Field(default_factory=list)
    # "pending": narration was started on demand; poll the same POST /guide/katha until "ready" (audio filled).
    audio_status: Literal["ready", "pending", "none"] | None = None


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


class TripDraft(_Model):
    """What intake understood from free text so far; every field optional. Sent on needs_input so a client
    can show the trip form pre-filled instead of only asking questions."""

    origin: str | None = None
    destinations: list[str] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    budget_inr: int | None = Field(default=None, ge=0)
    pace: Pace | None = None
    travellers: list[Traveller] = Field(default_factory=list)
    # A stated way to travel ("by train"); None when not said or "not sure" (compare all).
    transport_mode: Mode | None = None
    budget_style: BudgetStyle | None = None


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
    # On needs_input: the fields understood so far, to pre-fill the trip form.
    draft: TripDraft | None = None
    # On checking events: what the checker found this round.
    violations: list[Violation] = Field(default_factory=list)
    # Repair round 1..3 on checking and repairing events.
    iteration: int | None = Field(default=None, ge=1, le=3)
    # On error: whether trying again may help.
    retryable: bool = False
    # On done: opaque id for POST /plan/{plan_id}/revise.
    plan_id: str | None = None
    # On done: token for the read-only share link GET /trips/{share_token}.
    share_token: str | None = None


class ReviseIntent(StrEnum):
    lighter_day = "lighter_day"
    swap_stop = "swap_stop"
    rain = "rain"
    move_day = "move_day"
    transport = "transport"
    add_stop = "add_stop"
    remove_stop = "remove_stop"
    move_stop = "move_stop"
    change_stay = "change_stay"
    budget_style = "budget_style"
    booked = "booked"
    rest_of_day = "rest_of_day"


class BookedJourney(_Model):
    """A train or flight the traveller has already booked (ReviseIntent.booked)."""

    mode: Mode
    # Train number or flight number, e.g. "17309" or "6E 512".
    ref: str = Field(min_length=1, max_length=20)
    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    depart: datetime
    arrive: datetime

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _times_in_order(self) -> BookedJourney:
        if self.arrive < self.depart:
            raise ValueError("arrive must not be before depart")
        return self


class ReviseRequest(_Model):
    """Body of POST /plan/{plan_id}/revise. The response streams PlanEvents like /plan; done keeps the
    trip's plan_id and share_token (one trip, a new version).

    lighter_day: day. swap_stop: place_id. rain: optional day (all days when missing). move_day: city (that
    destination gains a day from a neighbour). transport: mode (every journey switches, stops are kept).
    add_stop: place (a name; a corpus place id works too) or place_id, optional day (else the best-fitting
    day). remove_stop: place_id. move_stop: place_id and day. change_stay: stay_id, or stay_pick "cheaper" or
    "better_rated", optional city. budget_style: style. booked: booked (the plan is re-timed around it).
    rest_of_day: now, optional lat and lng (today's remaining stops are re-planned from there; the stay
    and the journey home are kept)."""

    intent: ReviseIntent
    day: date | None = None
    place_id: str | None = None
    city: str | None = None
    mode: Mode | None = None
    lang: Lang | None = None
    place: str | None = Field(default=None, max_length=200)
    stay_id: str | None = None
    stay_pick: Literal["cheaper", "better_rated"] | None = None
    style: BudgetStyle | None = None
    booked: BookedJourney | None = None
    # rest_of_day: the traveller's local time and position.
    now: datetime | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _needs(self) -> ReviseRequest:
        i = ReviseIntent
        need = {
            i.lighter_day: (self.day is not None, "lighter_day needs day"),
            i.swap_stop: (bool(self.place_id), "swap_stop needs place_id"),
            i.move_day: (bool(self.city), "move_day needs city"),
            i.transport: (self.mode is not None, "transport needs mode"),
            i.add_stop: (bool(self.place or self.place_id), "add_stop needs place or place_id"),
            i.remove_stop: (bool(self.place_id), "remove_stop needs place_id"),
            i.move_stop: (bool(self.place_id) and self.day is not None, "move_stop needs place_id and day"),
            i.change_stay: (bool(self.stay_id or self.stay_pick), "change_stay needs stay_id or stay_pick"),
            i.budget_style: (self.style is not None, "budget_style needs style"),
            i.booked: (self.booked is not None, "booked needs booked"),
            i.rest_of_day: (self.now is not None, "rest_of_day needs now"),
        }
        ok, message = need.get(self.intent, (True, ""))
        if not ok:
            raise ValueError(message)
        return self


# Accounts, consent and ratings (TY4 P3; endpoints not built yet).


class Consents(_Model):
    """Purpose-specific opt-ins; all off until the user turns them on (DPDP)."""

    plan_history: bool = False
    location: bool = False
    analytics: bool = False


class ConsentsUpdate(_Model):
    """Body of PUT /me/consents: only the fields to change."""

    plan_history: bool | None = None
    location: bool | None = None
    analytics: bool | None = None


class Me(_Model):
    uid: str
    email: str | None = None
    name: str | None = None
    consents: Consents = Field(default_factory=Consents)
    consents_updated_at: datetime | None = None


class TripSummary(_Model):
    """One row of GET /me/trips per trip (its latest version), most recently changed first."""

    plan_id: str
    share_token: str
    title: str
    origin: str
    destinations: list[str]
    start_date: date
    end_date: date
    created_at: datetime
    # When the latest version was saved (created_at for a trip never revised).
    updated_at: datetime | None = None
    # The way the plan travels (the chosen mode, else the outbound journey's), and how many travel.
    mode: Mode | None = None
    travellers: int = Field(default=1, ge=1)
    total_inr: int | None = Field(default=None, ge=0)


class SavedPlan(_Model):
    """GET /plan/{plan_id}: the owner's own trip, latest version, to reopen it editable."""

    plan_id: str
    share_token: str
    itinerary: Itinerary
    version: int = Field(default=1, ge=1)
    updated_at: datetime | None = None


class RatingIn(_Model):
    """Body of POST /ratings; anonymous is fine, and no personal data belongs in it."""

    plan_id: str | None = None
    score: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)
    lang: Lang = Lang.en
