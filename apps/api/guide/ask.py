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

from ty_contracts import Citation, GuideAnswer, GuideQuestion, Place

from .places import PlacesClient
from .planner import corpus_city
from .retrieval.retrieve import Filters, Hit, TripContext, search

K = 5  # sources handed to the model: fewer tokens in, a faster answer (card #40)
MAX_TOKENS = 800  # an answer is about 100 tokens; the rest is headroom
EMERGENCY_NUMBER = "112"  # India's single emergency number: police, fire, ambulance
AMBULANCE_NUMBER = "108"  # the ambulance service in Goa, Karnataka and most states
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
URGENT_RESULTS = 20  # the most Nearby returns; one call either way
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
MINOR_CARE = re.compile(r"clinic|health cent|dispensary|\bdr\.?\s|polyclinic|diagnostic|nursing home", re.I)
#: Small care with beds: a hospital word does not lift these past real hospitals.
SMALL_WITH_BEDS = re.compile(r"clinic|nursing home|health cent|dispensary", re.I)
#: Never care for a patient, whatever else the name says ("Pharmax Medical Stores", live).
NOT_CARE = re.compile(r"pharmac|chemist|medical (store|shop|hall)|medicals\b|\blabs?\b|laborator", re.I)
#: ...unless the name also says it is a hospital ("Sample Clinic and Hospital").
HOSPITAL_WORD = re.compile(r"hospital|medical college|trauma", re.I)
MINOR_TYPES = {"doctor", "medical_clinic", "dental_clinic"}
NOT_CARE_TYPES = {"medical_lab", "pharmacy", "drugstore"}


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
    if row:
        return row[0], float(row[1]), float(row[2])
    # Spellings, filler words and Hindi/Kannada names, as Katha matches them (WA-11).
    from .katha.facts import _poi_by_name_or_slug

    if hit := _poi_by_name_or_slug(db, name):
        row = db.execute("SELECT lat, lng FROM poi WHERE id = %s", (hit[0],)).fetchone()
        return (hit[0], float(row[0]), float(row[1])) if row else None
    return None


#: "hospital near Panaji", "police station in Calangute": the place the traveller named.
#: Every preposition is a starting point, so "at my hotel in Panaji" still finds Panaji.
PREPOSITION = re.compile(r"\b(?:near|in|at|around|close to|nearest to)\s+(?:the\s+)?", re.I)
NAME_AT = re.compile(
    r"([^\W\d][\w'.-]*(?:\s+(?!(?:near|in|at|around|please|now|urgently|today|tonight)\b)"
    r"[^\W\d][\w'.-]*){0,3}?)\s*(?=[?.!,]|$|\s+(?:near|in|at|around|please|now|urgently|today|tonight)\b)",
    re.I,
)
#: Never places, however they are written ("at night", "in the car", "at the station").
NOT_A_PLACE = {
    "me", "here", "my", "our", "this", "that", "a", "an", "case", "emergency", "india", "pain",
    "trouble", "danger", "the", "it", "there", "hotel", "night", "morning", "evening", "afternoon",
    "day", "car", "taxi", "cab", "auto", "bus", "train", "flight", "station", "airport", "road",
    "street", "highway", "beach", "time", "hurry", "front", "back", "middle", "town", "city",
}  # fmt: skip
#: A Places match further than this from the traveller's stop or city is someone else's place.
NAMED_MAX_KM = 150


def named_place(question: str) -> str | None:
    """The place a question names for its help, if any ("near Panaji" -> "Panaji"): a name
    written as one (capitalised) or a corpus city however it is written ("near panaji")."""
    for p in PREPOSITION.finditer(question):
        m = NAME_AT.match(question, p.end())
        if not m:
            continue
        name = m.group(1).strip(" .")
        words = name.lower().split()
        if not words or name.lower() in NOT_A_PLACE or words[0] in NOT_A_PLACE or len(name) < 3:
            continue
        if name[0].isupper() or corpus_city(name):
            return name
    return None


def _city_centre(db: Any, city: str | None) -> tuple[float, float] | None:
    if not city:
        return None
    row = db.execute(
        "SELECT avg(lat), avg(lng) FROM poi WHERE lower(city) = lower(%s)", (corpus_city(city) or city,)
    ).fetchone()
    return (float(row[0]), float(row[1])) if row and row[0] is not None else None


def _locate(
    db: Any, req: GuideQuestion, places: PlacesClient | None = None
) -> tuple[float, float] | None:
    return locate(db, req, places)[0]


def locate(
    db: Any, req: GuideQuestion, places: PlacesClient | None = None
) -> tuple[tuple[float, float] | None, str | None]:
    """(where to search for help, the place it is near when the question named one).
    Where: the place the question names (a corpus place, or Google's match for the name
    near the trip); else the traveller; else their stop; else their city. A named place
    wins over the traveller's position: "hospitals near Panaji" is asked from elsewhere."""
    here = (req.lat, req.lng) if req.lat is not None and req.lng is not None else None
    stop = _poi(db, req.place_name, req.city) if not here else None
    known = here or ((stop[1], stop[2]) if stop else _city_centre(db, req.city))
    if name := named_place(req.question):
        if poi := _poi(db, name, req.city):
            return (poi[1], poi[2]), name
        try:  # one cached Text Search (Pro): "Panaji" -> Panaji, not the middle of Goa
            found = places.search(f"{name}, India", limit=1) if places else []
        except Exception:  # no key, quota, network: fall back to the stop and city
            found = []
        if found and (known is None or _km(*known, found[0].lat, found[0].lng) <= NAMED_MAX_KM):
            return (found[0].lat, found[0].lng), name
    return known, None


def _km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)  # fmt: skip
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def care_tier(place: Place) -> int:
    """0 a major hospital, 1 a hospital, 2 a small one ("X Nursing Home Hospital",
    "X Clinic and Hospital"), 3 a clinic, health centre, lab or doctor. Small care wins
    over a big name: "Apollo Clinic" is a clinic."""
    name = place.name
    if place.category in NOT_CARE_TYPES or NOT_CARE.search(name):
        return 3
    hospital = bool(HOSPITAL_WORD.search(name))
    if (place.category in MINOR_TYPES or MINOR_CARE.search(name)) and not hospital:
        return 3
    if hospital and SMALL_WITH_BEDS.search(name):
        return 2
    if MAJOR_HOSPITAL.search(name):  # "Dr. X Memorial Hospital" or "... & Diagnostic Centre" too
        return 0
    return 1 if place.category == "hospital" or hospital else 3


#: Ad copy Google Maps listings carry after the name: "X Hospital | Multispeciality Hospital
#: in Bengaluru", "Y Clinic - Best Dentist in Panaji". A branch ("Z Hospital - Old Airport
#: Road") stays.
AD_TAIL = re.compile(
    r"\s+[-–—:]\s+(?=.*\b(?:best|top|leading|no\.?\s?1|#1|24\s?[x/]\s?7|multi-?speciality|super-?speciality"
    r"|hospital in|clinic in|restaurant in|in [A-Z]\w+\s*$"
    # a bare category after the name ("GTR - Vegetarian Restaurant", live in Mysuru)
    r"|(?:pure\s+)?(?:veg\w*|multi-?cuisine|south indian|north indian|family)?\s*"
    r"(?:restaurants?|hotel|caf[eé]|hospitals?|clinic|pharmacy|chemists?|medicals?)\s*$))",
    re.I,
)


def clean_name(name: str) -> str:
    """A place's name without the ad copy Google Maps listings add after "|" or " - "."""
    name = re.split(r"\s+[|｜]\s*", name.strip(), maxsplit=1)[0]
    name = AD_TAIL.split(name, maxsplit=1)[0]
    return name.strip(" ,-–—|") or name


def _clean(place: Place) -> Place:
    return place.model_copy(update={"name": clean_name(place.name)})


def answer_emergency(
    kinds: list[str],
    where: tuple[float, float] | None,
    places: PlacesClient | None,
    *,
    urgent: bool = False,
    near: str | None = None,
) -> GuideAnswer:
    """The numbers, then the nearest help. The places go in emergency_places only: the
    clients list each with its map link, so a citation would list it twice (HQ P7)."""
    lines = [f"In an emergency, call {EMERGENCY_NUMBER} (police, fire and ambulance, all India) "
             f"or {AMBULANCE_NUMBER} for an ambulance."]
    if where is None:
        lines.append("Share your location and I can list the nearest help from Google Maps.")
        return GuideAnswer(text=" ".join(lines))
    found: list[Place] = []
    you = f"near {near}" if near else "near you"
    for kind in kinds:
        # Every hospital question ranks hospitals above clinics (WA-19); urgent ones also
        # say to go to a full hospital.
        bigger = kind == "hospital"
        try:
            nearby = (places.nearby_emergency(*where, kind, radius_m=URGENT_RADIUS_M, limit=URGENT_RESULTS,
                                              rank="POPULARITY")
                      if bigger else places.nearby_emergency(*where, kind)) if places else []  # fmt: skip
        except Exception:  # no key, quota, network: say so, never fill the gap
            lines.append(f"I couldn't reach Google Maps for {KIND_LABEL[kind]} just now.")
            continue
        if not nearby:
            km = (URGENT_RADIUS_M if bigger else 10000) // 1000
            lines.append(f"Google Maps lists no {KIND_LABEL[kind]} within {km} km of "
                         f"{near or 'you'}.")  # fmt: skip
            continue
        if bigger:
            nearby = sorted(nearby, key=lambda p: (care_tier(p), _km(*where, p.lat, p.lng)))
        items = []
        for place in map(_clean, nearby[:3]):
            found.append(place)
            items.append(f"{place.name} ({_km(*where, place.lat, place.lng):.1f} km)")
        if bigger and urgent:
            lines.append("For this, go to a full hospital, not a clinic. Hospitals "
                         f"{you}, larger ones first (likelier to have an emergency department; "
                         "call ahead): " + "; ".join(items) + ".")  # fmt: skip
        elif bigger:
            lines.append(f"Hospitals {you}, larger ones first: " + "; ".join(items) + ".")
        else:
            lines.append(f"{KIND_LABEL[kind].capitalize()} {you}: " + "; ".join(items) + ".")
    return GuideAnswer(text=" ".join(lines), emergency_places=found)


#: Everyday help near the traveller (HQ P8): (label, Places type, radius m, rank).
Need = tuple[str, str, int, str]
PHARMACY: Need = ("pharmacies", "pharmacy", 3000, "DISTANCE")
RESTAURANT: Need = ("restaurants", "restaurant", 2500, "POPULARITY")
VEG: Need = ("vegetarian restaurants", "vegetarian_restaurant", 3000, "POPULARITY")
ATM: Need = ("ATMs", "atm", 2000, "DISTANCE")
ATM_WORDS = re.compile(r"\batms?\b|cash ?machine|cash ?point|withdraw (?:cash|money)|need (?:some )?cash", re.I)
FOOD_WORDS = re.compile(
    r"restaurants?|places? to eat|eater(?:y|ies)|where (?:can|to|should|do) (?:i|we) eat|\b(?:lunch|dinner|"
    r"breakfast)\b|\bfood\b|dhaba|\bthali|\bcaf[eé]s?\b|something to eat|hungry",
    re.I,
)
VEG_WORDS = re.compile(r"(?<!non-)(?<!non )\b(?:pure )?veg(?:etarian|gie)?\b|\bjain\b|no meat", re.I)
#: A meal question is about the place's food ("what is Udupi food?") unless it asks for
#: somewhere near, or the traveller shared where they are.
NEAR_CUE = re.compile(r"\b(?:near|nearby|nearest|closest|around|close to|close by|walking distance|open now)\b", re.I)
#: A medicine question that is an emergency, not an errand.
DANGER = re.compile(r"overdose|poison|swallow|allerg|seizure|vomiting blood|not waking|suicid", re.I)


def nearby_need(req: GuideQuestion) -> Need | None:
    q = req.question
    if ATM_WORDS.search(q):
        return ATM
    located = req.lat is not None and req.lng is not None
    if FOOD_WORDS.search(q) and (NEAR_CUE.search(q) or located):
        return VEG if VEG_WORDS.search(q) else RESTAURANT
    return None


def answer_nearby(
    need: Need, where: tuple[float, float] | None, places: PlacesClient | None, *, near: str | None = None
) -> GuideAnswer:
    """Up to five places from Google Maps, clean names and distances in the text; the places
    themselves in emergency_places, which every client lists with a short map link."""
    label, place_type, radius_m, rank = need
    if where is None:
        return GuideAnswer(text=f"Share your location, or name the place you're at, and I'll list "
                                f"{label} near you from Google Maps.")  # fmt: skip
    try:
        found = places.nearby(*where, place_type, radius_m=radius_m, limit=5, rank=rank) if places else []
    except Exception:  # no key, quota, network: say so, never fill the gap
        return GuideAnswer(text=f"I couldn't reach Google Maps for {label} just now. Try again in a minute.")
    you = f"near {near}" if near else "near you"
    if not found:
        return GuideAnswer(text=f"Google Maps lists no {label} within {radius_m / 1000:g} km {you}.")
    found = sorted(map(_clean, found), key=lambda p: _km(*where, p.lat, p.lng))
    items = "; ".join(f"{p.name} ({_km(*where, p.lat, p.lng):.1f} km)" for p in found)
    return GuideAnswer(text=f"{label[0].upper()}{label[1:]} {you}, from Google Maps: {items}. "
                            "Check the hours before you go.", emergency_places=found)  # fmt: skip


#: GET /guide/nearby kinds. hospital ranks as every hospital question does (WA-19).
NEARBY_KINDS: dict[str, Need] = {"food": RESTAURANT, "veg": VEG, "atm": ATM, "pharmacy": PHARMACY,
                                 "hospital": ("hospitals", "hospital", URGENT_RADIUS_M, "POPULARITY")}  # fmt: skip


def nearby_list(places: PlacesClient, lat: float, lng: float, kind: str, limit: int = 3) -> list[dict]:
    """[{name, kind, lat, lng, distance_m, maps_url}], nearest first (hospitals: larger
    ones first), clean names. One cached Nearby Search (Pro)."""
    _, place_type, radius_m, rank = NEARBY_KINDS[kind]
    big = kind == "hospital"
    found = places.nearby(lat, lng, place_type, radius_m=radius_m, limit=URGENT_RESULTS if big else 5, rank=rank)
    found = sorted(map(_clean, found), key=lambda p: ((care_tier(p) if big else 0), _km(lat, lng, p.lat, p.lng)))
    return [{
        "name": p.name, "kind": kind, "lat": p.lat, "lng": p.lng,
        "distance_m": round(_km(lat, lng, p.lat, p.lng) * 1000),
        "maps_url": f"https://www.google.com/maps/search/?api=1&query={p.lat:.5f},{p.lng:.5f}&query_place_id={p.id}",
    } for p in found[:limit]]  # fmt: skip


#: "When does the Taj Mahal open?": hours come from Google Maps or are not given (HQ P9).
#: Opening-time phrasing only: "what time is best to visit", "how many hours do I need" and
#: "is it open to non-Hindus" are guide questions (review P1).
HOURS_Q = re.compile(
    r"\b(?:what|which) time\b.*\b(?:open|close|shut)|\b(?:opening|closing|visiting) (?:time|hour)s?\b|\btimings?\b"
    r"|\bopen (?:on|at|today|now|till|until|tomorrow|tonight|late|daily|every)\b|\bis\b.*\bopen\s*\??\s*$"
    r"|\bwhen (?:does|do|is|will)\b.*\b(?:open|close|shut)|\bclosed? (?:on|at|today|tomorrow)\b|\bcloses (?:at|on)\b"
    r"|खुल(?:ता|ती|ने|ेगा)|बंद (?:होता|होती|रहता|रहती)|कितने बजे",
    re.I,
)
CHECK_HOURS = "Check hours before you go."
_DAY_NAMES = {"mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat", "sun": "Sun"}


def asked_place(question: str, place_name: str | None) -> dict | None:
    """The corpus place an hours question is about: the longest corpus name the question
    contains ("Taj Mahal", not "Taj"), else the stop it was asked at ("when does it open?")."""
    from . import names
    from .planner import _pois

    q = f" {names.normalize(question)} "
    pois = _pois()
    hindi = {v: k for k, v in names.NATIVE.items()}  # the demo subjects' Hindi names

    def forms(p: dict) -> list[str]:
        return [p["name"], p.get("name_kn") or "", *(p.get("names") or {}).values(), hindi.get(p["name"], "")]

    raw = f" {names._fold(question)} "  # Hindi as written: normalize() turns ताजमहल into "taj mahal"
    found = [(len(n), p) for p in pois for f in forms(p)
             for n, text in ((names.normalize(f), q), (names._fold(f), raw)) if n and f" {n} " in text]
    if found:
        return max(found, key=lambda x: x[0])[1]
    return next((p for p in pois if p["name"].lower() == place_name.lower()), None) if place_name else None


def format_hours(hours: list) -> str:
    """"Mon-Thu, Sat-Sun 06:00-18:30; closed Fri", days with the same times grouped."""
    order = list(_DAY_NAMES)
    by_day: dict[str, list[str]] = {}
    for h in hours:
        by_day.setdefault(h.day, []).append(f"{h.opens:%H:%M}-{h.closes:%H:%M}")
    groups: list[tuple[list[str], str]] = []
    for d in order:
        if d not in by_day:
            continue
        times = ", ".join(by_day[d])
        if groups and groups[-1][1] == times and order.index(groups[-1][0][-1]) == order.index(d) - 1:
            groups[-1][0].append(d)
        else:
            groups.append(([d], times))
    parts = [(f"{_DAY_NAMES[g[0]]}-{_DAY_NAMES[g[-1]]}" if len(g) > 1 else _DAY_NAMES[g[0]]) + f" {t}"
             for g, t in groups]
    closed = [_DAY_NAMES[d] for d in order if d not in by_day]
    return "; ".join(parts) + (f"; closed {', '.join(closed)}" if closed else "")


def answer_hours(poi: dict) -> GuideAnswer:
    """Google Maps' regular hours for a corpus place with a place_id, or none at all: a
    place without them is never given guessed hours."""
    from .hours import live_hours
    from .planner import place_ids, to_place

    place = live_hours([to_place(poi)])[0]
    if not place.opening_hours:
        return GuideAnswer(text=f"I don't have reliable opening hours for {place.name}. {CHECK_HOURS}")
    source = "Google Maps" if place.id in place_ids() else "Travel Yantra field notes"
    return GuideAnswer(text=f"{place.name}: {format_hours(place.opening_hours)} ({source}, regular hours). "
                            f"Holidays and events can change them; {CHECK_HOURS[0].lower()}{CHECK_HOURS[1:]}")


SYSTEM = """You are Travel Yantra's guide for travellers in India.
Answer the question using only the numbered sources below. Rules:
- Two to four plain sentences. No lists, no headings.
- Put the source number in square brackets right after each claim it supports, like [2].
- A source marked (legend) is folklore: say so ("Legend says...", "The story goes..."),
  never state it as fact.
- If the sources do not answer the question, reply exactly: NO_ANSWER
- Do not add facts, dates, prices or names that are not in the sources.
- Never mention the sources themselves ("Based on the provided sources", "The sources do
  not say"): answer as a guide who knows, or reply NO_ANSWER."""


def build_prompt(question: str, sources: list[Hit]) -> str:
    blocks = []
    for n, hit in enumerate(sources, start=1):
        label = " (legend)" if hit.is_legend else ""
        place = f" [{hit.city}]" if hit.city else ""
        blocks.append(f"[{n}]{label}{place} {hit.title or ''}\n{hit.body}")
    return f"{SYSTEM}\n\nSources:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"


#: The model talking about its sources instead of the place (HQ P7): an opening to cut...
SOURCE_LEAD = re.compile(
    r"(?:^|(?<=[.!?]\s))(?:based (?:only )?on|according to|from) (?:the )?(?:provided |given |available )?"
    r"(?:sources?|information|context|documents?)(?: provided)?,?\s*",
    re.I,
)
#: ...and a sentence to drop: "The sources do not provide...", "The provided sources don't say".
SOURCE_GAP = re.compile(
    r"\b(?:the |these |my )?(?:provided |given |available )?(?:sources?|information|context|documents?)"
    r"(?: provided)? (?:do(?:es)? not|don'?t|doesn'?t|did not|never) (?:provide|say|mention|specify|"
    r"include|contain|state|cover|give|describe|offer)|\bnot (?:mentioned|specified|stated|provided) in the "
    r"(?:provided )?(?:sources?|information|context)",
    re.I,
)


def no_source_talk(text: str) -> str:
    """The answer without talk about its sources: such sentences are dropped and such
    openings cut; what is left starts with a capital."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [s for s in sentences if not SOURCE_GAP.search(s)]
    out = []
    for s in kept:
        s = SOURCE_LEAD.sub("", s)
        out.append(s[:1].upper() + s[1:] if s else s)
    return " ".join(s for s in out if s)


def ground(text: str, sources: list[Hit]) -> GuideAnswer | None:
    """Keep markers that point at a real source, renumber them in order of first
    use, and build citations to match. None when nothing valid is cited."""
    if "NO_ANSWER" in text:
        return None
    text = no_source_talk(text)
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
    kinds = emergency_kinds(req.question)
    danger = URGENT.search(req.question) or DANGER.search(req.question)
    need = PHARMACY if kinds == ["pharmacy"] and not danger else None if kinds else nearby_need(req)
    if need:  # everyday help on the trip: a pharmacy, a meal, cash; no 112 header for these
        where, near = locate(db, req, places)
        return answer_nearby(need, where, places, near=near)
    if not kinds and HOURS_Q.search(req.question) and (poi := asked_place(req.question, req.place_name)):
        import asyncio

        return await asyncio.to_thread(answer_hours, poi)  # Places Details, cached a week
    if kinds:
        urgent = bool(URGENT.search(req.question))
        where, near = locate(db, req, places)
        return answer_emergency(kinds, where, places, urgent=urgent, near=near)
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
