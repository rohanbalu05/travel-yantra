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
from collections.abc import Callable
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
    "Kochi": [("wikivoyage", "Kochi"), ("wikipedia", "Kochi")],
    "Munnar": [("wikivoyage", "Munnar"), ("wikipedia", "Munnar")],
    "Alleppey": [("wikivoyage", "Alappuzha"), ("wikipedia", "Alappuzha")],
    "Delhi": [("wikivoyage", "Delhi"), ("wikipedia", "Climate of Delhi")],
    "Agra": [("wikivoyage", "Agra"), ("wikipedia", "Agra")],
    "Jaipur": [("wikivoyage", "Jaipur"), ("wikipedia", "Jaipur")],
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


#: A note that names a festival is an event: it holds only on the festival's dates, not
#: the whole month (WA-02, WEB-09: Dasara lights quoted for a 31 Oct trip, after Dasara).
EVENT = re.compile(r"\b(dasara|dussehra|navaratri|navratri|festival|utsav|carnival|christmas|diwali|"
                   r"deepavali|shigmo|feast|jatre|jatra|illuminated|boat race|mahotsav|onam|holi|teej|"
                   r"gangaur|biennale|vallam kali)\w*", re.I)  # fmt: skip
#: Festival dates, by the words that name them. A year not listed is unknown, and an event
#: whose dates are unknown is left out of a dated trip rather than guessed.
EVENT_DATES: list[tuple[re.Pattern, Callable[[int], tuple[date, date] | None]]] = [
    # Mysuru Dasara: Navaratri to Vijayadashami. 2026: 11-20 October.
    (re.compile(r"dasara|dussehra|navaratri|navratri|mysore palace is illuminated", re.I),
     lambda y: {2026: (date(2026, 10, 11), date(2026, 10, 20))}.get(y)),
    # Hampi Utsav, as the quoted source says: "the first week of November".
    (re.compile(r"hampi utsav", re.I), lambda y: (date(y, 11, 1), date(y, 11, 7))),
    (re.compile(r"christmas", re.I), lambda y: (date(y, 12, 24), date(y, 12, 25))),
    # Nehru Trophy Boat Race, Punnamada Lake: the second Saturday of August.
    (re.compile(r"nehru trophy", re.I), lambda y: (_nth_saturday(y, 8, 2),) * 2),
    # Taj Mahotsav, Shilpgram, Agra: 18-27 February every year.
    (re.compile(r"taj mahotsav", re.I), lambda y: (date(y, 2, 18), date(y, 2, 27))),
]  # fmt: skip


def _nth_saturday(y: int, m: int, n: int) -> date:
    return date(y, m, 1 + (5 - date(y, m, 1).weekday()) % 7 + 7 * (n - 1))


def notes_for(city: str, month: int | date) -> list[dict]:
    """[{text, source_url, kind}] for a destination in a month (1-12 or a date). kind is
    "month" when the source names that month, "general" for the destination's climate
    (the contract's SeasonNote kinds). A festival note is listed for its whole month here;
    notes_for_trip keeps it only inside the trip."""
    m = month.month if isinstance(month, date) else month
    return list(_table().get(corpus_city(city) or city, {}).get(MONTHS[m - 1], []))


def is_event(note: dict) -> bool:
    return bool(EVENT.search(note["text"]))


def event_window(text: str, year: int) -> tuple[date, date] | None:
    """The dates a festival note holds in that year, or None if they are not known."""
    for pattern, dates in EVENT_DATES:
        if pattern.search(text):
            return dates(year)
    return None


#: Notes about an activity, not the season a traveller lands in (HQ P7: Goa showed two
#: diving notes). The planner's season notes are about weather and festivals.
ACTIVITY = re.compile(r"\b(div(?:e|ing|ers?)|scuba|snorkel\w*|surf\w*|trek\w*|raft\w*|parasail\w*|kayak\w*|"
                      r"paraglid\w*|fishing|angling|safari\w*|bird ?watch\w*|camping)\b", re.I)  # fmt: skip
#: A season word in a general note, and the months it is true in. "Enjoy Coorg in the
#: monsoon season" is not a note for November (HQ P7).
SEASON_MONTHS = {
    # Kerala's second rains: October to December, so not "the monsoon" of June to September.
    re.compile(r"north[- ]?east(ern)? monsoon|retreating monsoon", re.I): {10, 11, 12},
    re.compile(r"(?<!east )(?<!east-)(?<!northeast )(?<!retreating )monsoon|rainy season|the rains\b", re.I):
        {6, 7, 8, 9},
    re.compile(r"\bwinter", re.I): {11, 12, 1, 2},
    re.compile(r"\bsummer", re.I): {3, 4, 5, 6},
}
_Q = r"(mid-|mid |early |late |the end of |end of )?"
WINDOW = re.compile(rf"\b{_Q}{_MONTH}\b\.?\s*(?:to|till|until|through|-|–)\s*{_Q}{_MONTH}\b", re.I)


def _last_day(y: int, m: int) -> int:
    return ((date(y + (m == 12), m % 12 + 1, 1)) - date(y, m, 1)).days


def windows(text: str, year: int) -> list[tuple[date, date]]:
    """The date ranges a sentence names, to the half month ("mid-November to mid-February"
    is 15 Nov to 15 Feb), each in the year given and the one before, so a range across
    New Year still meets a January trip."""
    out = []
    for m in WINDOW.finditer(text):
        q1, q2 = ((m.group(i) or "").strip().lower() for i in (1, 3))
        a, b = _index(m.group(2)) + 1, _index(m.group(4)) + 1
        for y in (year - 1, year):
            yb = y + (b < a)
            d1 = {"mid-": 15, "mid": 15, "late": 21, "the end of": 21, "end of": 21}.get(q1, 1)
            d2 = {"early": 10, "mid-": 15, "mid": 15}.get(q2, _last_day(yb, b))
            out.append((date(y, a, d1), date(yb, b, d2)))
    return out


def fits_trip(note: dict, start: date, end: date) -> bool:
    """A note the trip's actual dates make true: no activity notes; a named range must meet
    the trip's days, not just its month; a general monsoon/winter/summer note only in those
    months."""
    text = note["text"]
    if ACTIVITY.search(text):
        return False
    if spans := windows(text, start.year) + windows(text, end.year):
        return any(a <= end and b >= start for a, b in spans)
    # No range read: a season word must be true in the trip's months, whatever kind the
    # note is ("monsoon ... late June ... mid-September" also names November: HQ P7).
    months, d = set(), start.replace(day=1)
    while d <= end:
        months.add(d.month)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    for pattern, true_in in SEASON_MONTHS.items():
        if pattern.search(text) and not months & true_in:
            return False
    return True


def notes_for_trip(city: str, start: date, end: date) -> list[dict]:
    """Notes for every month of a trip, once each, with each event kept only when its
    dates fall inside the trip (an event with unknown dates is left out), and every note
    checked against the trip's dates (fits_trip)."""
    out: list[dict] = []
    seen: set[str] = set()
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        for note in notes_for(city, m):
            if note["text"] in seen or not fits_trip(note, start, end):
                continue
            if is_event(note):
                window = event_window(note["text"], y)
                if not window or window[1] < start or window[0] > end:
                    continue
            seen.add(note["text"])
            out.append(note)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


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
