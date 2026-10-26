"""Pre-approved UI and plan phrases per language. Hits never reach the model."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

PHRASEBOOK_FILE = Path(__file__).with_name("phrasebook.tsv")


@lru_cache(maxsize=1)
def load(path: Path = PHRASEBOOK_FILE) -> dict[str, dict[str, str]]:
    """English phrase -> {lang: text}."""
    with path.open(encoding="utf-8", newline="") as f:
        rows = csv.DictReader(f, delimiter="\t")
        return {r["en"]: {k: v for k, v in r.items() if k != "en"} for r in rows}


def lookup(text: str, target: str, book: dict[str, dict[str, str]] | None = None) -> str | None:
    book = load() if book is None else book
    return book.get(text.strip(), {}).get(target)
