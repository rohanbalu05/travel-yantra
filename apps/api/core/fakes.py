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


class FakeModel:
    """Deterministic stand-in for Gemini. Intake reads the city, origin and dates of the two samples."""

    async def json(self, prompt: str, schema: type[BaseModel], tier: str = "lite") -> BaseModel:
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

    async def text(self, prompt: str, tier: str = "flash") -> str:
        first = prompt.strip().splitlines()[0]
        return f"(sample) {first[:120]}"
