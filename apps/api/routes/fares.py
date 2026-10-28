"""One fare model for every leg TY3 prices: compare's options, the planner's stop-to-stop
legs (through the road provider) and the IRCTC card all call these functions, so a fare
for the same ride is the same number everywhere.

- Rail: per person, by class. Indian Railways fares taper with distance, so the sleeper
  fare is a power curve fitted to published sleeper fares (about Rs 380 for 650 km,
  Rs 800 for 2,180 km, Rs 185 at the 200 km sleeper minimum; IRCTC fare enquiry,
  2025), times a class multiplier, with the class's minimum charged distance. An estimate:
  IRCTC shows the real fare when you book.
- Driving your own or a hired car: fuel per km plus tolls on known expressways, per car.
- Cab (getting around a city, to and from stations and airports): base plus per km, with a
  minimum fare, per cab.
All are reversible assumptions, listed in the README."""
from __future__ import annotations

import math
from typing import Literal

RailClass = Literal["2S", "SL", "CC", "3E", "3A", "2A", "1A", "EC"]
BudgetStyle = Literal["budget", "mid", "luxury"]
# TY1's Constraints.budget_style words are accepted too.
STYLE_ALIASES = {"shoestring": "budget", "comfort": "mid"}


def style_key(style: str | None) -> str | None:
    """budget | mid | luxury for either vocabulary; None stays None."""
    return STYLE_ALIASES.get(style, style) if style else None

# Rail. Sleeper fare per person = SL_A * km ** SL_P (fitted, see the module note).
SL_A, SL_P = 7.1, 0.615
CLASS_FARE: dict[str, float] = {"2S": 0.6, "SL": 1.0, "CC": 2.2, "3E": 2.4, "3A": 2.6, "2A": 3.7, "EC": 4.3,
                                "1A": 6.2}
MIN_KM: dict[str, float] = {"SL": 200, "3E": 250, "3A": 250, "2A": 250, "1A": 250}  # minimum charged distance
# The class each budget style rides, best first; a train is priced in the first class it carries.
STYLE_CLASSES: dict[str, tuple[str, ...]] = {
    "budget": ("SL", "2S", "CC", "3E", "3A"),
    "mid": ("3A", "CC", "3E", "SL", "2A", "2S"),
    "luxury": ("2A", "1A", "EC", "3A", "CC"),
}
DEFAULT_STYLE: BudgetStyle = "mid"

# Driving. Petrol about Rs 103/L (PPAC retail selling price, Bengaluru, 2025; Delhi about
# Rs 95) at 15 km/L for a hatchback or small sedan: Rs 6.9 a km, rounded to 7.
FUEL_INR_PER_KM = 7.0
SEATS_PER_CAR = 4
# Car tolls one way on known expressways (NHAI fee plazas, 2024-25, approximate).
TOLLS_INR: dict[frozenset[str], int] = {
    frozenset({"bengaluru", "mysuru"}): 325,  # Bengaluru-Mysuru Expressway, two plazas
    frozenset({"mumbai", "pune"}): 320,  # Mumbai-Pune Expressway
    frozenset({"mumbai", "lonavala"}): 270,  # Mumbai-Pune Expressway, Khalapur plaza
    frozenset({"delhi", "agra"}): 415,  # Yamuna Expressway, Greater Noida-Agra
    frozenset({"delhi", "mathura"}): 250,  # Yamuna Expressway, Jewar and Mathura plazas
    frozenset({"delhi", "jaipur"}): 500,  # Delhi-Mumbai Expressway, Sohna-Dausa, and NH48
}

# Cabs. App-cab city fares (Ola/Uber mini, 2025, approximate): Rs 60 + Rs 18 a km, at least Rs 100.
CAB_BASE_INR, CAB_INR_PER_KM, CAB_MIN_INR = 60.0, 18.0, 100.0


def rail_class(classes: list[str] | tuple[str, ...], style: str | None = None) -> str:
    """The class a party of this budget style rides on a train carrying `classes`."""
    for c in STYLE_CLASSES.get(style_key(style) or DEFAULT_STYLE, STYLE_CLASSES[DEFAULT_STYLE]):
        if c in classes:
            return c
    return classes[0] if classes else "2S"


def rail_fare(km: float, cls: str) -> int:
    """Per person, in rupees."""
    km = max(km, MIN_KM.get(cls, 0.0), 1.0)
    return math.ceil(SL_A * km ** SL_P * CLASS_FARE[cls])


def cars(people: int) -> int:
    return max(1, math.ceil(people / SEATS_PER_CAR))


def toll(a: str, b: str) -> int:
    """One car's tolls between two city keys (compare.CITIES), 0 when none is known."""
    return TOLLS_INR.get(frozenset({a, b}), 0)


def drive_cost(km: float, toll_inr: int = 0, people: int = 1) -> int:
    """Fuel and tolls for the cars the party needs."""
    return round(km * FUEL_INR_PER_KM + toll_inr) * cars(people)


def cab_fare(km: float, people: int = 1) -> int:
    """One cab (or more, four to a cab) across town."""
    return round(max(CAB_MIN_INR, CAB_BASE_INR + km * CAB_INR_PER_KM)) * cars(people)
