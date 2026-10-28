"""Reading a message without a model: its language, a story request, a trip, a destination,
a cancel, and the keyword edits. Anything these miss goes to Flash-Lite (edits) or the guide."""

from __future__ import annotations

import re

from ty_contracts import Lang

LANG_WORDS = {
    "english": Lang.en,
    "hindi": Lang.hi,
    "हिंदी": Lang.hi,
    "हिन्दी": Lang.hi,
    "kannada": Lang.kn,
    "ಕನ್ನಡ": Lang.kn,
    "tamil": Lang.ta,
    "தமிழ்": Lang.ta,
    "telugu": Lang.te,
    "తెలుగు": Lang.te,
    "bengali": Lang.bn,
    "bangla": Lang.bn,
    "বাংলা": Lang.bn,
}
_LANG = "|".join(LANG_WORDS)
# "story Mysore Palace", "katha of Hampi 5 min in Hindi", "कथा मैसूर पैलेस", "मैसूर पैलेस की कहानी"
STORY = re.compile(
    r"^\s*(?:(?:tell\s+(?:me\s+)?)?(?:the\s+|a\s+)?(?:story|katha|kahani)(?:\s+of|\s+about)?"
    r"|कथा|कहानी)\s+(?P<what>.+?)"
    rf"(?:\s+(?P<min>2|5|10)\s*(?:min(?:ute)?s?|मिनट))?(?:\s+(?:in\s+)?(?P<lang>{_LANG})(?:\s+में)?)?"
    r"\s*[.!?।]?\s*$"
    r"|^\s*(?P<what2>.+?)\s+(?:की|का)\s+(?:कथा|कहानी)\s*[.!?।]?\s*$",
    re.IGNORECASE,
)
FORGET = re.compile(
    r"^\s*(?:please\s+)?(?:delete|erase|remove|forget)\s+"
    r"(?:(?:all\s+)?my\s+(?:data|details|chats?|history)|me|everything\s+about\s+me)\b"
    r"|डेटा\s*(?:हटा|मिटा|डिलीट)",
    re.IGNORECASE,
)
GREETINGS = {
    "hi",
    "hello",
    "hey",
    "help",
    "namaste",
    "start",
    "नमस्ते",
    "ನಮಸ್ಕಾರ",
    "வணக்கம்",
    "నమస్కారం",
    "নমস্কার",
}
# "cancel", "close the trip", "end this plan", "start over"; the whole message, so "cancel my
# train" is not one.
CANCEL = re.compile(
    r"^\s*(?:please\s+)?(?:(?:cancel|close|end|stop|drop|forget|discard|scrap|reset)"
    r"(?:\s+(?:the|this|my|that))?(?:\s+(?:trip|plan|draft|itinerary|holiday))?"
    r"|start\s+(?:over|again|afresh)|new|new\s+trip)\s*[.!]?\s*$"
    r"|^\s*(?:यात्रा|ट्रिप|प्लान)\s*(?:रद्द|कैंसल|बंद)",
    re.IGNORECASE,
)

# Unicode blocks of the Indic scripts we support; Hinglish (Latin script) counts as English.
SCRIPTS = {
    Lang.hi: (0x0900, 0x097F),
    Lang.bn: (0x0980, 0x09FF),
    Lang.ta: (0x0B80, 0x0BFF),
    Lang.te: (0x0C00, 0x0C7F),
    Lang.kn: (0x0C80, 0x0CFF),
}

_MONTH = r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
MONTHS = {
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep",
    "sept", "oct", "nov", "dec",
}  # fmt: skip
# Trip words in English, Hinglish and the five Indic scripts.
TRIP_WORDS = re.compile(
    r"\b(?:plan|trip|itinerary|holiday|vacation|tour|yatra|safar)\b"
    r"|यात्रा|सफ़र|सफर|घूमने|ಪ್ರವಾಸ|ಯಾತ್ರೆ|பயண|சுற்றுலா|ప్రయాణ|యాత్ర|పర్యటన|ভ্রমণ|বেড়াতে|যাত্রা",
    re.IGNORECASE,
)
# "Bengaluru to Goa" / "Bengaluru se Goa" together with a date: a trip even without a trip word.
ROUTE = re.compile(r"[A-Za-z]\s+(?:to|se)\s+[A-Za-z]", re.IGNORECASE)
DATE = re.compile(rf"\d|\b(?:{_MONTH})|\b(?:today|tomorrow|weekend|next\s+week)\b", re.IGNORECASE)
# A place a message names as where it goes: "to Goa", "visit Hampi", "Goa trip", "Coorg ki trip".
_PLACE = r"[A-Za-z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)?"
DEST = re.compile(
    rf"\b(?P<prep>to|se|visit|visiting|explore|for|in)\s+(?P<a>{_PLACE})"
    rf"|(?P<b>{_PLACE})\s+(?:ki\s+|ka\s+)?(?:trip|holiday|tour|vacation|yatra)\b",
)
NOT_PLACES = {
    "a", "an", "the", "me", "us", "my", "our", "you", "it", "go", "be", "do", "see", "visit",
    "plan", "trip", "day", "days", "night", "nights", "week", "weekend", "people", "person",
    "adults", "kids", "children", "family", "friends", "couple", "budget", "train", "flight",
    "bus", "car", "road", "rail", "air", "travel", "stay", "hotel", "relax", "relaxed", "eat",
    "food", "this", "that", "next", "some", "two", "three", "four", "five", "each", "all",
    "total", "now", "today", "tomorrow", "december", "short", "long", "quick", "day trip",
    "family trip", "road trip", "weekend trip", "honeymoon", "pilgrimage", "solo", "group",
    "summer", "winter", "monsoon", "diwali", "christmas", "new", "year", "holidays",
}  # fmt: skip
# A message about a ticket already bought: with a plan, it is the booked edit, never a new trip.
BOOKING = re.compile(
    r"\b(?:booked|bought|got\s+(?:the\s+)?tickets?|tickets?\s+(?:for|on)|pnr)\b"
    # A 5-digit train number, or an airline code in capitals ("6E 512", "AI-803"), not "in 20".
    r"|\b(?:train|flight)\s+(?:no\.?\s*)?(?:\d{5}|(?-i:[A-Z]{2}|[A-Z]\d|\d[A-Z])\s?-?\d{2,4})\b"
    r"|बुक\s*(?:किया|कर\s*लिया)|टिकट",
    re.IGNORECASE,
)
QUESTION_START = re.compile(
    r"^\s*(?:what|where|when|which|who|whom|whose|why|how|is|are|can|could|should|do|does|"
    r"will|would|tell\s+me|any|kya|kaun|kahan|kab|kaise|kitna)\b",
    re.IGNORECASE,
)


def detect_lang(text: str) -> Lang:
    counts = {lang: 0 for lang in SCRIPTS}
    for ch in text:
        for lang, (lo, hi) in SCRIPTS.items():
            if lo <= ord(ch) <= hi:
                counts[lang] += 1
    lang, n = max(counts.items(), key=lambda kv: kv[1])
    return lang if n else Lang.en


def parse_story(text: str) -> tuple[str, int, Lang | None] | None:
    """(subject, minutes, language asked for) for a story request; None for anything else."""
    m = STORY.match(text)
    if not m:
        return None
    what = (m["what"] or m["what2"] or "").strip(" .,")
    if not what:
        return None
    lang = LANG_WORDS.get((m["lang"] or "").lower()) if m["lang"] else None
    return what, int(m["min"] or 2), lang


def is_trip(text: str) -> bool:
    return bool(TRIP_WORDS.search(text) or (ROUTE.search(text) and DATE.search(text)))


def is_question(text: str) -> bool:
    return text.rstrip().endswith(("?", "？")) or bool(QUESTION_START.match(text))


def destinations(text: str, strict: bool = False) -> list[str]:
    """Places the message names as where to go, in order ("Plan Bengaluru to Goa" -> ["Goa"]).
    strict: only "to X", "visit X", "X trip" (not "for X" or "in X", which may name a person or
    a part of the trip)."""
    out = []
    for m in DEST.finditer(text):
        if strict and (m["prep"] or "").lower() in ("for", "in"):
            continue
        name = (m["a"] or m["b"]).strip(" .'-")
        words = name.split()
        # "to Goa in" -> keep "Goa"; a second word only when capitalised ("Mysore Palace").
        while words and words[-1].casefold() in NOT_PLACES | MONTHS:
            words.pop()
        name = " ".join(words)
        low = name.casefold()
        if not name or low in NOT_PLACES or low in MONTHS or any(ch.isdigit() for ch in name):
            continue
        if low not in (o.casefold() for o in out):
            out.append(name)
    return out


def is_full_trip(text: str) -> bool:
    """A whole new trip in one message: where to, and when ("Plan Bengaluru to Mysuru 3-4 Nov")."""
    return bool(destinations(text)) and is_trip(text) and bool(DATE.search(text))


def same_place(a: str, names: list[str]) -> bool:
    """"Goa" matches "North Goa"; "Mysore" matches "Mysuru" (old and new spellings)."""
    a = _norm(a)
    if not a:
        return False
    return any(b and (a in b or b in a) for b in (_norm(n) for n in names))


SPELLINGS = {
    "bangalore": "bengaluru",
    "mysore": "mysuru",
    "bombay": "mumbai",
    "madras": "chennai",
    "calcutta": "kolkata",
    "pondicherry": "puducherry",
    "trivandrum": "thiruvananthapuram",
    "cochin": "kochi",
    "mangalore": "mangaluru",
    "coorg": "kodagu",
    "ooty": "udhagamandalam",
    "gurgaon": "gurugram",
}


def _norm(name: str) -> str:
    """Lower case, each old spelling replaced word by word ("Mysore Palace" -> "mysuru palace")."""
    # Split on spaces, digits and punctuation only: Indic vowel signs are not \w and must stay.
    words = re.findall(r"[^\s\d.,;:!?'\"()/&+_\-–—।]+", name.casefold())
    return " ".join(SPELLINGS.get(w, w) for w in words)


# Keyword edits once a plan exists. Keywords stay English in the hints so users can copy them.
_END = r"(?=\s|$|[.,!?])"
SHARE = re.compile(rf"^\s*(?:share|link|शेयर|ಹಂಚಿ|பகிர்|షేర్|শেয়ার){_END}", re.IGNORECASE)
LIGHTER = re.compile(rf"\b(?:lighter|easier|relaxed|halka){_END}|हल्का", re.IGNORECASE)
RAIN = re.compile(
    rf"\b(?:rain|raining|rainy|baarish|barish){_END}|बारिश|ಮಳೆ|மழை|వర్షం|বৃষ্টি", re.IGNORECASE
)
MOVE_DAY = re.compile(
    r"\b(?:(?:an?\s+)?(?:extra|another|one\s+more)\s+day|more\s+(?:time|days?)|add\s+a\s+day"
    r"|move\s+a\s+day)\s+(?:in|at|to|for)\s+(?P<city>[^\d?!.,]+)",
    re.IGNORECASE,
)
SWAP = re.compile(r"^\s*(?:swap|replace|change)\s+(?P<what>.+)$", re.IGNORECASE)
REMOVE = re.compile(r"^\s*(?:remove|drop|skip|cut|delete)\s+(?P<what>.+)$", re.IGNORECASE)
ADD = re.compile(
    r"^\s*(?:add|include|also\s+(?:see|visit))\s+(?P<what>.+?)"
    r"(?:\s+(?:on|to|in)\s+(?:day\s*(?P<day>\d{1,2})|the\s+(?P<nth>\d{1,2})(?:st|nd|rd|th)\s+day))?"
    r"\s*[.!]?\s*$",
    re.IGNORECASE,
)
# "more places on day 2", "another place", "something else to do on day 3": add, place not named.
ADD_MORE = re.compile(
    r"\b(?:more|another|other|one\s+more|something\s+else|anything\s+else|extra)\s+"
    r"(?:places?|stops?|sights?|things?(?:\s+to\s+(?:do|see))?|to\s+(?:do|see)|activit(?:y|ies))\b",
    re.IGNORECASE,
)
MOVE_STOP = re.compile(
    r"^\s*(?:move|shift|put)\s+(?P<what>.+?)\s+(?:to|on|onto)\s+day\s*(?P<day>\d{1,2})\s*[.!]?\s*$",
    re.IGNORECASE,
)
STAY = re.compile(
    r"\b(?P<pick>cheaper|less\s+expensive|budget|better|better[-\s]rated|nicer)\s+"
    r"(?:hotel|stay|room|place\s+to\s+stay)s?\b",
    re.IGNORECASE,
)
STYLE = re.compile(
    r"\b(?:make\s+it\s+|go\s+|on\s+a\s+|switch\s+to\s+)?(?P<style>shoestring|backpacker|luxury|"
    r"luxurious|comfort|comfortable)(?:\s+(?:budget|trip|style|plan))?\b",
    re.IGNORECASE,
)
MODE = re.compile(
    r"^\s*(?:let'?s\s+|we(?:'ll|\s+will)\s+|i(?:'ll|\s+will)\s+)?"
    r"(?:(?:go|travel|switch\s+to|change\s+to)\s+)?"
    r"(?:by\s+)?(?P<mode>train|rail|bus|car|road|cab|taxi|flight|air|plane|fly)"
    r"(?:\s+(?:instead|please|only))?\s*[.!]?\s*$",
    re.IGNORECASE,
)
LATE = re.compile(
    r"\b(?:running|we(?:'re| are)|i(?:'m| am))?\s*(?:late|delayed|behind)\b"
    r"(?:\s+by\s+(?P<a>\d{1,3})\s*(?P<au>h|hr|hrs|hours?|m|mins?|minutes?))?"
    r"|\b(?P<b>\d{1,3})\s*(?P<bu>h|hr|hrs|hours?|m|mins?|minutes?)\s+(?:late|behind)\b",
    re.IGNORECASE,
)
DAY_N = re.compile(
    r"\bday\s*(?P<a>\d{1,2})\b|\b(?P<b>\d{1,2})(?:st|nd|rd|th)?\s+day\b", re.IGNORECASE
)
MODES = {
    "train": "rail", "rail": "rail", "bus": "road", "car": "road", "road": "road", "cab": "road",
    "taxi": "road", "flight": "air", "air": "air", "plane": "air", "fly": "air",
}  # fmt: skip
STYLES = {
    "shoestring": "shoestring", "backpacker": "shoestring", "luxury": "luxury",
    "luxurious": "luxury", "comfort": "comfort", "comfortable": "comfort",
}  # fmt: skip


def day_number(text: str) -> int | None:
    m = DAY_N.search(text)
    return int(m["a"] or m["b"]) if m else None


def late_minutes(text: str) -> int | None:
    """Minutes late for "running late" (30 when it says no number); None when it is not that."""
    m = LATE.search(text)
    if not m or not re.search(r"\blate|delayed|behind\b", text, re.IGNORECASE):
        return None
    n, unit = (m["a"], m["au"]) if m["a"] else (m["b"], m["bu"])
    if not n:
        return 30
    return int(n) * (60 if unit.lower().startswith("h") else 1)


def keyword_edit(text: str) -> tuple[str, dict] | None:
    """(intent, fields) for the keyword edits; None when no rule matches. Fields name stops and
    cities as the user wrote them; the engine matches them to the plan."""
    if SHARE.search(text):
        return "share", {}
    if is_question(text):
        return None  # "is it raining in Goa?" is a question for the guide
    words = len(text.split())
    if mv := MOVE_DAY.search(text):
        return "move_day", {"city": mv["city"].strip()}
    if m := MOVE_STOP.match(text):
        return "move_stop", {"place": m["what"].strip(" ."), "day": int(m["day"])}
    if ADD_MORE.search(text) and words <= 12:
        return "add_stop", {"place": None, "day": day_number(text)}
    if m := ADD.match(text):
        day = m["day"] or m["nth"]
        return "add_stop", {"place": m["what"].strip(" ."), "day": int(day) if day else None}
    if m := REMOVE.match(text):
        return "remove_stop", {"place": m["what"].strip(" ."), "day": day_number(text)}
    if (m := STAY.search(text)) and words <= 8:
        pick = "cheaper" if m["pick"].lower() in ("cheaper", "less expensive", "budget") else None
        return "change_stay", {"stay_pick": pick or "better_rated"}
    if (m := MODE.match(text)) and words <= 6:
        return "transport", {"mode": MODES[m["mode"].lower()]}
    if (m := STYLE.search(text)) and words <= 6:
        return "budget_style", {"style": STYLES[m["style"].lower()]}
    if (late := late_minutes(text)) is not None and words <= 10:
        return "rest_of_day", {"minutes": late}
    if s := SWAP.match(text):
        return "swap_stop", {"place": s["what"].strip(" ."), "day": day_number(text)}
    if RAIN.search(text) and words <= 6:
        return "rain", {"day": day_number(text)}
    if LIGHTER.search(text) and words <= 6:
        return "lighter_day", {"day": day_number(text)}
    return None


# The regions Travel Yantra plans (HQ): their cities and common spellings. Origins can be anywhere.
REGIONS = {
    "Karnataka": [
        "Karnataka", "Bengaluru", "Bangalore", "Mysuru", "Mysore", "Hampi", "Coorg", "Kodagu",
        "Madikeri", "Chikmagalur", "Chikkamagaluru", "Gokarna", "Udupi", "Mangaluru", "Mangalore",
        "Badami", "Aihole", "Pattadakal", "Belur", "Halebidu", "Hassan", "Shivamogga", "Jog Falls",
        "Kabini", "Bandipur", "Dandeli", "Murudeshwar", "Sakleshpur", "Srirangapatna", "Bijapur",
        "Vijayapura", "Hubli", "Dharwad", "Karwar", "Nandi Hills", "Kudremukh", "Shravanabelagola",
        "Nagarhole", "Chitradurga", "Sringeri", "Bidar", "Kalaburagi", "Gulbarga", "Tumakuru",
        "Tumkur", "Ramanagara", "Belagavi", "Belgaum", "Ballari", "Bellary", "Kolar", "Mandya",
        "Bhatkal", "Agumbe", "Talakaveri", "Bylakuppe", "Kemmangundi", "Kodachadri",
    ],
    "Goa": [
        "Goa", "Panaji", "Panjim", "Madgaon", "Margao", "Vasco", "Calangute", "Baga", "Anjuna",
        "Palolem", "Candolim", "Mapusa", "Old Goa", "Colva", "Agonda", "Arambol",
    ],
    "Kerala": [
        "Kerala", "Kochi", "Cochin", "Munnar", "Alleppey", "Alappuzha", "Thiruvananthapuram",
        "Trivandrum", "Kovalam", "Varkala", "Wayanad", "Thekkady", "Kumarakom", "Kozhikode",
        "Calicut", "Thrissur", "Kollam", "Kannur", "Vagamon", "Athirappilly", "Fort Kochi",
        "Ernakulam", "Idukki", "Palakkad", "Kottayam", "Pathanamthitta", "Sabarimala",
        "Guruvayur", "Bekal", "Kasaragod", "Poovar", "Marari", "Thenmala", "Malappuram",
    ],
    "Golden Triangle": [
        "Golden Triangle", "Delhi", "New Delhi", "Agra", "Jaipur", "Fatehpur Sikri", "Mathura",
        "Vrindavan", "Amber", "Amer", "Old Delhi", "Pink City",
    ],
}  # fmt: skip
COVERED = [c for cities in REGIONS.values() for c in cities]


_COVERED_NORM = [_norm(c) for c in COVERED]


def covered(text: str) -> bool:
    """Whether the text names a place in our regions, as whole words ("Mysore Palace", "visit
    Kerala backwaters"; never "Cameroon" for Amer)."""
    words = f" {_norm(text)} "
    return any(f" {c} " in words for c in _COVERED_NORM)


def outside_regions(names: list[str], text: str = "") -> list[str]:
    """The named places, if every one is outside the regions we plan and the message names no
    covered place anywhere ("Ooty and Goa" is a Goa trip); else []."""
    # Only after the first "to" / "visit": the origin ("Bengaluru to Manali") can be anywhere.
    where = re.search(r"\b(?:to|se|visit|visiting|explore)\b", text, re.IGNORECASE)
    rest = text[where.start() :] if where else text
    if not names or any(covered(n) for n in names) or covered(rest):
        return []
    return names
