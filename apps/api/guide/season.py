"""Season scout (card #39): weather, season and festival notes per destination and month.

Notes are sentences quoted from Wikivoyage (and Wikipedia where Wikivoyage is
thin), each with its page URL. A sentence that names months ("June to October",
"mid-November to mid-February", "the first week of November") is filed under
those months; a climate sentence that names none is a general note. Nothing is
written by a model and nothing is paraphrased.

The table is data/season/notes.json, built by `python -m guide.season`.
"""

from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache

from .planner import corpus_city
from .retrieval.seed import DATA

PATH = DATA / "season" / "notes.json"
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_MONTH = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
          r"sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")  # fmt: skip
RANGE = re.compile(rf"\b{_MONTH}\b\.?\s*(?:to|till|until|through|-|–)\s*(?:mid-|early |late )?{_MONTH}\b", re.I)
SINGLE = re.compile(rf"\b{_MONTH}\b", re.I)
SEASON_WORDS = re.compile(r"\b(climate|monsoon|winter|summer|rain|rainfall|humid|temperature|"
                          r"best time|season|festival|utsav|dasara|carnival|christmas|fog)\w*", re.I)  # fmt: skip
NOISE = re.compile(r"\bas of\b|\bupdated\b|₹|rs\.?\s?\d|\bprice|\bcharge|\bfare|\bticket", re.I)
SECTIONS = re.compile(r"introduction|understand|climate|when to go|weather|festival|events|geography|"
                      r"name and history|do|culture|public holidays", re.I)  # fmt: skip

#: Corpus city -> pages to read, in order of preference.
PAGES = {
    "Mysuru": [("wikivoyage", "Mysore")],
    "Hampi": [("wikivoyage", "Hampi"), ("wikipedia", "Hampi"), ("wikipedia", "Hosapete"), ("wikipedia", "Vijayanagara district")],
    "Bengaluru": [("wikivoyage", "Bangalore")],
    "Chikmagalur": [("wikivoyage", "Chikmagalur"), ("wikipedia", "Chikmagalur")],
    "Coorg": [("wikivoyage", "Kodagu"), ("wikipedia", "Kodagu district"), ("wikipedia", "Madikeri")],
    "Goa": [("wikivoyage", "Goa")],
}
MAX_PER_MONTH = 4


def _index(name: str) -> int:
    return MONTHS.index(name[:3].lower())


def months_in(sentence: str) -> list[str]:
    """The months a sentence is about: every month in a range, plus single mentions."""
    found: set[int] = set()
    for m in RANGE.finditer(sentence):
        a, b = _index(m.group(1)), _index(m.group(2))
        found.update(i % 12 for i in range(a, a + ((b - a) % 12) + 1))
    for m in SINGLE.finditer(RANGE.sub(" ", sentence)):
        if m.group(1).lower() != "may" or re.search(r"\b(in|of|to|from|until) may\b", sentence, re.I):
            found.add(_index(m.group(1)))  # "may" the verb is not the month
    return [MONTHS[i] for i in sorted(found)]


def notes_from(sections: list[tuple[str, str]], url: str) -> tuple[dict[str, list], list[dict]]:
    by_month: dict[str, list] = {m: [] for m in MONTHS}
    general: list[dict] = []
    for heading, body in sections:
        if not SECTIONS.search(heading):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
            sentence = " ".join(sentence.split())
            if len(sentence.split()) < 6 or NOISE.search(sentence) or not SEASON_WORDS.search(sentence):
                continue
            note = {"text": sentence, "source_url": url}
            months = months_in(sentence)
            for m in months:
                by_month[m].append({**note, "kind": "month"})
            if not months and re.search(r"(?i)climate|monsoon|rain|winter|temperature|best time", sentence):
                general.append({**note, "kind": "general"})
    return by_month, general


def build(wiki) -> dict:
    table = {}
    for city, pages in PAGES.items():
        by_month: dict[str, list] = {m: [] for m in MONTHS}
        general: list[dict] = []
        for site, page in pages:
            url, sections = wiki.sections(page, site=site)
            months, gen = notes_from(sections, url)
            for m in MONTHS:
                by_month[m] += months[m]
            general += gen
        table[city] = {
            m: (by_month[m][:MAX_PER_MONTH] or general[:2]) for m in MONTHS
        }
    return table


@lru_cache(maxsize=1)
def _table() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))["notes"] if PATH.exists() else {}


def notes_for(city: str, month: int | date) -> list[dict]:
    """[{text, source_url, kind}] for a destination in a month (1-12 or a date). kind is
    "month" when the source names that month, "general" for the destination's climate."""
    m = month.month if isinstance(month, date) else month
    return list(_table().get(corpus_city(city) or city, {}).get(MONTHS[m - 1], []))


def main() -> None:
    from .wiki import WikiClient

    wiki = WikiClient()
    table = build(wiki)
    PATH.parent.mkdir(exist_ok=True)
    note = (f"Built by `python -m guide.season` from Wikivoyage and Wikipedia on "
            f"{date.today().isoformat()}. Sentences are quoted, CC BY-SA; each keeps its page URL.")  # fmt: skip
    PATH.write_text(json.dumps({"note": note, "notes": table}, ensure_ascii=False, indent=1), encoding="utf-8")
    for city, months in table.items():
        print(city, {m: sum(n["kind"] == "month" for n in months[m]) or ("general" if months[m] else "NONE")
                     for m in ("oct", "nov", "dec", "jan")})  # fmt: skip
    print(f"Wikimedia requests: {wiki.calls}")


if __name__ == "__main__":
    main()
