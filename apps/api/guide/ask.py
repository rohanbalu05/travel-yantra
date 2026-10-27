"""POST /guide/ask: sourced answers to a traveller's question.

Two paths, chosen by keywords before any model is involved:

- Emergency (hospital, police, pharmacy): the answer is a template filled from
  Google Places Nearby. No model writes it, so it cannot invent a hospital.
- Everything else: hybrid retrieval over the corpus, then one Gemini call that
  may only use the numbered sources and must cite them as [n]. No hits, or an
  answer that cites nothing, becomes a plain "I don't know".

`text` carries the [n] markers and `citations[n-1]` is the source behind each,
so a translator can work on `text` alone and leave the markers in place.
"""

from __future__ import annotations

import math
import re
from typing import Any, Protocol
from urllib.parse import quote

from ty_contracts import Citation, GuideAnswer, GuideQuestion, Place

from .places import PlacesClient
from .planner import corpus_city
from .retrieval.retrieve import Filters, Hit, TripContext, search

K = 5  # sources handed to the model: fewer tokens in, a faster answer (card #40)
MAX_TOKENS = 800  # an answer is about 100 tokens; the rest is headroom
EMERGENCY_NUMBER = "112"  # India's single emergency number: police, fire, ambulance
REFUSAL = (
    "I don't have a sourced answer to that yet, so I won't guess. "
    "Try asking about a specific place, its history, food or customs."
)

#: Checked in order; a question can need more than one kind.
EMERGENCY_WORDS = {
    "pharmacy": r"pharmac|chemist|medical (shop|store)|medicine|tablets?",
    "hospital": r"hospital|doctor|ambulance|clinic|injur|bleed|chest pain|heart attack"
    r"|unconscious|faint|snake ?bite|medical emergency|accident",
    "police": r"police|stolen|theft|thief|robbed|pickpocket|harass|lost my (passport|wallet|phone)",
}
KIND_LABEL = {"hospital": "hospitals", "police": "police stations", "pharmacy": "pharmacies"}
#: Cardiac or injury: a clinic or a health centre can't treat it, so full hospitals come
#: first, even a little further away.
URGENT = re.compile(
    r"chest pain|heart|cardiac|stroke|unconscious|faint|collapse|not breathing|can'?t breathe"
    r"|breathless|accident|injur|bleed|fractur|broken (arm|leg|bone|wrist|ankle)|snake ?bite|burn",
    re.I,
)
URGENT_RADIUS_M = 15000
URGENT_RESULTS = 10
#: Names that mean a hospital with casualty or emergency care. Places has no field for
#: an emergency department, so this is the best signal it gives: a heuristic, and said so.
MAJOR_HOSPITAL = re.compile(
    r"medical college|\bgmc\b|district hospital|civil hospital|government hospital|general hospital"
    r"|sub-?district|multi-?speciality|super-?speciality|multispecialty|trauma|emergency|casualty"
    r"|heart|cardiac|institute|\b(aiims|esi|manipal|apollo|fortis|narayana|aster|max|kims)\b"
    r"|columbia asia|healthcare city",
    re.I,
)
#: Small care, even under a big name ("Apollo Clinic", "Heart Clinic", "Max Lab").
MINOR_CARE = re.compile(
    r"clinic|health cent|dispensary|\bdr\.?\s|polyclinic|diagnostic|nursing home|\blabs?\b|laborator"
    r"|pharmac|chemist",
    re.I,
)
#: ...unless the name also says it is a hospital ("Sample Clinic and Hospital").
HOSPITAL_WORD = re.compile(r"hospital|medical college|trauma", re.I)
MINOR_TYPES = {"doctor", "medical_clinic", "medical_lab", "dental_clinic", "pharmacy", "drugstore"}


class Answerer(Protocol):
    async def __call__(self, question: str, sources: list[Hit]) -> str: ...


def emergency_kinds(question: str) -> list[str]:
    q = question.lower()
    return [kind for kind, pattern in EMERGENCY_WORDS.items() if re.search(pattern, q)]


def _poi(db: Any, name: str | None, city: str | None) -> tuple[int, float, float] | None:
    if not name:
        return None
    row = db.execute(
        "SELECT id, lat, lng FROM poi WHERE lower(name) = lower(%s) "
        "OR lower(name) LIKE lower(%s) || ',%%' OR lower(name) LIKE lower(%s) || ' (%%' "
        "ORDER BY (city = %s) DESC, length(name) LIMIT 1",
        (name, name, name, city),
    ).fetchone()
    return (row[0], float(row[1]), float(row[2])) if row else None


def _locate(db: Any, req: GuideQuestion) -> tuple[float, float] | None:
    """Where to search for help: the traveller, else their stop, else their city."""
    if req.lat is not None and req.lng is not None:
        return req.lat, req.lng
    if poi := _poi(db, req.place_name, req.city):
        return poi[1], poi[2]
    if req.city:
        row = db.execute(
            "SELECT avg(lat), avg(lng) FROM poi WHERE lower(city) = lower(%s)", (req.city,)
        ).fetchone()
        if row and row[0] is not None:
            return float(row[0]), float(row[1])
    return None


def _km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)  # fmt: skip
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def maps_url(place: Place) -> str:
    return (
        "https://www.google.com/maps/search/?api=1"
        f"&query={quote(place.name)}&query_place_id={quote(place.id)}"
    )


def care_tier(place: Place) -> int:
    """0 a major hospital, 1 a hospital, 2 a small one ("X Nursing Home Hospital",
    "X Clinic and Hospital"), 3 a clinic, health centre, lab or doctor. Small care wins
    over a big name: "Apollo Clinic" is a clinic."""
    name = place.name
    minor = place.category in MINOR_TYPES or bool(MINOR_CARE.search(name))
    if minor:
        return 2 if HOSPITAL_WORD.search(name) else 3
    if MAJOR_HOSPITAL.search(name):
        return 0
    return 1 if place.category == "hospital" or HOSPITAL_WORD.search(name) else 3


def answer_emergency(
    kinds: list[str],
    where: tuple[float, float] | None,
    places: PlacesClient | None,
    *,
    urgent: bool = False,
) -> GuideAnswer:
    lines = [f"In an emergency, call {EMERGENCY_NUMBER} (police, fire and ambulance, all India)."]
    if where is None:
        lines.append("Share your location and I can list the nearest help from Google Maps.")
        return GuideAnswer(text=" ".join(lines))
    found: list[Place] = []
    citations: list[Citation] = []
    for kind in kinds:
        bigger = urgent and kind == "hospital"
        try:
            nearby = (places.nearby_emergency(*where, kind, radius_m=URGENT_RADIUS_M, limit=URGENT_RESULTS)
                      if bigger else places.nearby_emergency(*where, kind)) if places else []  # fmt: skip
        except Exception:  # no key, quota, network: say so, never fill the gap
            lines.append(f"I couldn't reach Google Maps for {KIND_LABEL[kind]} just now.")
            continue
        if not nearby:
            lines.append(f"Google Maps lists no {KIND_LABEL[kind]} within 10 km of you.")
            continue
        if bigger:
            nearby = sorted(nearby, key=lambda p: (care_tier(p), _km(*where, p.lat, p.lng)))
        items = []
        for place in nearby[:3]:
            found.append(place)
            citations.append(Citation(title=f"Google Maps: {place.name}", url=maps_url(place)))
            items.append(f"{place.name}, {_km(*where, place.lat, place.lng):.1f} km [{len(citations)}]")
        if bigger:
            lines.append("For this, go to a full hospital, not a clinic. Hospitals, larger ones "
                         "first (likelier to have an emergency department; call ahead): "
                         + "; ".join(items) + ".")  # fmt: skip
        else:
            lines.append(f"Nearest {KIND_LABEL[kind]}: " + "; ".join(items) + ".")
    return GuideAnswer(text=" ".join(lines), citations=citations, emergency_places=found)


SYSTEM = """You are Travel Yantra's guide for travellers in India.
Answer the question using only the numbered sources below. Rules:
- Two to four plain sentences. No lists, no headings.
- Put the source number in square brackets right after each claim it supports, like [2].
- A source marked (legend) is folklore: say so ("Legend says...", "The story goes..."),
  never state it as fact.
- If the sources do not answer the question, reply exactly: NO_ANSWER
- Do not add facts, dates, prices or names that are not in the sources."""


def build_prompt(question: str, sources: list[Hit]) -> str:
    blocks = []
    for n, hit in enumerate(sources, start=1):
        label = " (legend)" if hit.is_legend else ""
        place = f" [{hit.city}]" if hit.city else ""
        blocks.append(f"[{n}]{label}{place} {hit.title or ''}\n{hit.body}")
    return f"{SYSTEM}\n\nSources:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"


def ground(text: str, sources: list[Hit]) -> GuideAnswer | None:
    """Keep markers that point at a real source, renumber them in order of first
    use, and build citations to match. None when nothing valid is cited."""
    if "NO_ANSWER" in text:
        return None
    order: list[int] = []

    def renumber(m: re.Match) -> str:
        n = int(m.group(1))
        if not 1 <= n <= len(sources):
            return ""
        if n not in order:
            order.append(n)
        return f"[{order.index(n) + 1}]"

    # [1, 3] and [1][3] both come back from models; split the first into the second.
    text = re.sub(r"\[(\d+(?:\s*,\s*\d+)+)\]",
                  lambda m: "".join(f"[{n.strip()}]" for n in m.group(1).split(",")), text)  # fmt: skip
    text = re.sub(r"\[(\d+)\]", renumber, text)
    text = re.sub(r"\s+([.,;])", r"\1", re.sub(r"[ \t]{2,}", " ", text)).strip()
    if not order:
        return None
    citations = []
    for n in order:
        hit = sources[n - 1]
        title = hit.title or hit.city or "Travel Yantra guide"
        if hit.source_name:
            title = f"{title} ({hit.source_name})"
        citations.append(Citation(title=title, url=hit.source_url))
    return GuideAnswer(text=text, citations=citations)


async def ask(
    req: GuideQuestion,
    db: Any,
    answerer: Answerer,
    places: PlacesClient | None = None,
    *,
    retrieve=None,
) -> GuideAnswer:
    if kinds := emergency_kinds(req.question):
        urgent = bool(URGENT.search(req.question))
        return answer_emergency(kinds, _locate(db, req), places, urgent=urgent)
    # place_id is accepted but not matched: the corpus does not store itinerary ids yet.
    poi = _poi(db, req.place_name, req.city)
    # city is a soft hint: the plan's destination, not necessarily what the question is
    # about ("Who built Mysore Palace?" asked on a Goa trip). Narrow to it first, and
    # search everywhere when it is not a corpus city or finds nothing.
    city = corpus_city(req.city) if req.city and not poi else None
    context = TripContext(current_poi=poi[0] if poi else None, has_elderly=req.has_elderly)
    hits = []
    for filters in ([Filters(city=city)] if city else []) + [None]:
        hits = (retrieve or search)(req.question, db, filters=filters, k=K, trip_context=context)
        if hits:
            break
    if not hits:
        return GuideAnswer(text=REFUSAL)
    return ground(await answerer(req.question, hits), hits) or GuideAnswer(text=REFUSAL)


class FakeAnswerer:
    """Cites the first sentence of the top two sources. No model, no network."""

    async def __call__(self, question: str, sources: list[Hit]) -> str:
        out = []
        for n, hit in enumerate(sources[:2], start=1):
            first = re.split(r"(?<=[.!?])\s", hit.body.strip(), maxsplit=1)[0].rstrip(".")
            out.append(f"{'Legend says ' if hit.is_legend else ''}{first} [{n}].")
        return " ".join(out)


class ModelAnswerer:
    """One short Flash call per question, through core.llm."""

    async def __call__(self, question: str, sources: list[Hit]) -> str:
        from core.llm import get_model

        # Minimal thinking: on Flash even "low" spent ~380 tokens thinking and the
        # answer was cut off at the cap. The sources already hold the reasoning.
        return await get_model().text(
            build_prompt(question, sources),
            tier="flash",
            thinking="minimal",
            max_output_tokens=MAX_TOKENS,
            temperature=0.2,
            label="guide ask",
        )


def answerer() -> Answerer:
    """The fake under TY_FAKE_LLM=1 (tests, local runs), otherwise the model."""
    from core.llm import fake_enabled

    return FakeAnswerer() if fake_enabled() else ModelAnswerer()
