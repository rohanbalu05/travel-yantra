"""Sample-backed data and the fake model. They read packages/contracts/samples; no model or network calls.

The data functions stand in for TY2's places and TY3's transport and stays until those lanes expose
planner functions (core/steps.py calls them directly).
"""

from __future__ import annotations

import json
import re
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from ty_contracts import Itinerary, Place, Stay, TransportOption, TripRequest

SAMPLES = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "samples"
BY_CITY = {"goa": "goa_family.json", "mysuru": "mysuru_weekend.json", "mysore": "mysuru_weekend.json"}


@lru_cache
def sample(name: str) -> Itinerary:
    data = json.loads((SAMPLES / name).read_text(encoding="utf-8"))
    return Itinerary.model_validate(data["itinerary"])


def sample_for(request: TripRequest) -> Itinerary | None:
    for d in request.destinations:
        if d.lower() in BY_CITY:
            return sample(BY_CITY[d.lower()])
    return None


def transport(request: TripRequest) -> list[TransportOption]:
    s = sample_for(request)
    return list(s.transport) if s else []


def places(request: TripRequest) -> list[Place]:
    s = sample_for(request)
    return [p for d in s.days for p in d.stops] if s else []


def stays(request: TripRequest) -> list[Stay]:
    s = sample_for(request)
    if not s:
        return []
    nights = max((request.end_date - request.start_date).days, 1)
    return [st.model_copy(update={"check_in": request.start_date,
                                  "check_out": request.start_date + timedelta(days=nights)}) for st in s.stays]


def _alt(pid: str, name: str, lat: float, lng: float, category: str, minutes: int) -> Place:
    hours = [{"day": d, "opens": "09:00", "closes": "17:00"} for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")]
    return Place.model_validate({"id": pid, "name": name, "lat": lat, "lng": lng, "category": category,
                                 "typical_visit_minutes": minutes, "opening_hours": hours, "source": "sample"})


# Sample alternatives beyond the sample itineraries, for revise (swap a stop, rain). Approximate coordinates.
ALTERNATIVES = {
    "goa_family.json": [
        _alt("goa-state-museum", "Goa State Museum", 15.4949, 73.8296, "museum", 60),
        _alt("goa-asi-museum", "Archaeological Museum, Old Goa", 15.5040, 73.9125, "museum", 45),
        _alt("goa-st-cajetan", "Church of St. Cajetan", 15.5048, 73.9145, "church", 30),
        _alt("goa-reis-magos", "Reis Magos Fort", 15.4977, 73.8094, "fort", 60),
        _alt("goa-dona-paula", "Dona Paula viewpoint", 15.4560, 73.8040, "viewpoint", 45),
    ],
    "mysuru_weekend.json": [
        _alt("mys-jaganmohan", "Jaganmohan Palace Art Gallery", 12.3064, 76.6496, "gallery", 60),
        _alt("mys-rail-museum", "Rail Museum", 12.3160, 76.6440, "museum", 45),
        _alt("mys-philomena", "St. Philomena's Church", 12.3209, 76.6584, "church", 30),
        _alt("mys-karanji", "Karanji Lake", 12.3020, 76.6740, "park", 60),
    ],
}


def alternatives(request: TripRequest) -> list[Place]:
    name = next((BY_CITY[d.lower()] for d in request.destinations if d.lower() in BY_CITY), None)
    return list(ALTERNATIVES.get(name, []))


class FakeModel:
    """Deterministic stand-in for Gemini. Intake reads the city, origin and dates of the two samples."""

    async def json(self, prompt: str, schema: type[BaseModel], tier: str = "lite", **_: object) -> BaseModel:
        from .intake import IntakeDraft

        if schema is not IntakeDraft:
            raise NotImplementedError(f"FakeModel has no answer for {schema.__name__}")
        text = prompt.rsplit("Message:\n", 1)[-1].lower()
        city = next((c for c in BY_CITY if c in text), None)
        req = sample(BY_CITY[city]).request if city else None
        has_dates = bool(re.search(r"\d", text))
        has_origin = any(w in text for w in ("bengaluru", "bangalore", "from"))
        return IntakeDraft(
            origin=req.origin if req and has_origin else None,
            destinations=req.destinations if req else [],
            start_date=req.start_date if req and has_dates else None,
            end_date=req.end_date if req and has_dates else None,
            budget_inr=req.constraints.budget_inr if req else None,
            pace=req.constraints.pace if req else None,
            travellers=[{"name": t.name, "age": t.age} for t in req.constraints.travellers] if req else [],
        )

    async def text(self, prompt: str, tier: str = "flash", *, label: str | None = None, **_: object) -> str:
        """Short canned text per call, so fake-mode screens read like a plan, not like a prompt."""
        canned = {
            "narrator": "(sample text) Your trip is ready: the days below are planned around opening hours and travel time.",
            "story": "(sample text) A short story about this place appears here when a model is connected.",
        }
        return canned.get(label or "", "(sample text) Model text appears here when a model is connected.")
