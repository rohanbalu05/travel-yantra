"""Ranked stays for a city, dates and party, from fictional sample data until
SerpApi Hotels (P2). Prices are per night for the whole party (rooms needed x
room rate). Cities use the same names and aliases as compare."""
from __future__ import annotations

import datetime as dt
import json
import math
from functools import lru_cache
from pathlib import Path

from ty_contracts import Stay

from .compare import UnknownPlace, resolve_city
from .graph import DATA_DIR


@lru_cache(maxsize=4)
def _stays(data_dir: Path = DATA_DIR) -> dict[str, list[dict]]:
    raw = json.loads((data_dir / "sample_stays.json").read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def rank_stays(city: str, check_in: dt.date, check_out: dt.date, party: int = 1,
               budget_per_night_inr: int | None = None, limit: int = 3,
               data_dir: Path = DATA_DIR) -> list[Stay]:
    """Stays that fit the budget first (best rating, then cheapest), then the
    rest by price. Raises UnknownPlace for a city outside the sample, and
    ValueError for bad dates or party."""
    if check_out <= check_in:
        raise ValueError("check_out must be after check_in")
    if party < 1:
        raise ValueError("party must be at least 1")
    node = resolve_city(city)
    rows = _stays(data_dir).get(node.id.removeprefix("PL:"))
    if not rows:
        raise UnknownPlace(f"no sample stays in {node.name}")
    priced = [(r, math.ceil(party / r["sleeps"]) * r["room_inr"]) for r in rows]

    def key(item: tuple[dict, int]):
        r, price = item
        fits = budget_per_night_inr is None or price <= budget_per_night_inr
        return (0, -r["rating"], price) if fits else (1, price, -r["rating"])

    return [Stay(name=r["name"], city=node.name, check_in=check_in, check_out=check_out,
                 price_per_night_inr=price)
            for r, price in sorted(priced, key=key)[:limit]]
