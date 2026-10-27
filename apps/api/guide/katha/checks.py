"""Katha checks from design/katha-style.md: slop, citations, labels and length.

Pure functions over (label, text) segments. A story that fails is regenerated,
never shipped. Grow BANNED when the taste gate finds more.

Other languages (rule 12) keep every English check, since English slop can leak
into a Hindi draft, and add their own banned phrases and legend cues.
"""

from __future__ import annotations

import re

#: Rule 11, verbatim where it is a phrase; a pattern where it is a shape.
BANNED = [
    "nestled", "rich tapestry", "tapestry", "testament to", "steeped in history",
    "hidden gem", "bustling", "vibrant", "breathtaking", "awe-inspiring", "delve",
    "step back in time", "boasts", "a must-visit", "must-visit", "must-see",
    "in conclusion", "a blend of", "timeless charm", "rich heritage", "nestled amidst",
]  # fmt: skip
WHETHER = re.compile(r"\bwhether you(?:'| a)re an? [^.?!]{1,40}? or an? ", re.I)

#: The same slop in Hindi: literal renderings of rule 11 that Hindi travel copy
#: leans on. Matched as substrings (word boundaries are unreliable in Devanagari).
BANNED_LANG = {
    "hi": [
        "ताना-बाना", "का प्रमाण है", "का जीता-जागता प्रमाण", "इतिहास में डूबा", "छिपा हुआ रत्न",
        "छुपा हुआ रत्न", "चहल-पहल भरा", "जीवंत", "लुभावन", "मनमोहक", "विस्मयकारी",
        "मंत्रमुग्ध कर", "समय में पीछे", "अवश्य देख", "ज़रूर देखें", "जरूर देखें",
        "निष्कर्ष में", "निष्कर्षतः", "का मिश्रण", "कालातीत", "समृद्ध विरासत", "गोद में बसा",
    ],
}  # fmt: skip

#: Read-aloud budgets (rule 10): about 300, 750 and 1,500 words.
BANDS = {2: (220, 400), 5: (580, 950), 10: (1150, 1850)}

#: Rule 9: a legend is told as a legend.
LEGEND_CUES = re.compile(
    r"people (here )?say|legend|the story goes|it is said|they say|is told|tell[s]? (of|how)"
    r"|according to (tradition|the story|local belief)|believe[sd]?|myth|tradition holds",
    re.I,
)
LEGEND_CUES_LANG = {
    "hi": re.compile(
        r"लोग कहते|कहा जाता|कहते हैं|किंवदंती|दंतकथा|लोककथा|कथा है|कहानी है कि|मान्यता|मानते हैं"
        r"|माना जाता|किस्सा|क़िस्सा|सुनाते हैं"
    ),
}


def legend_told(text: str, lang: str = "en") -> bool:
    cues = LEGEND_CUES_LANG.get(lang)
    return bool(LEGEND_CUES.search(text) or (cues and cues.search(text)))

#: Adjectives that turn up in stacked triples ("grand, ancient and majestic").
# Evaluative suffixes only: "carved, painted and gilded pillars" is concrete, not slop.
_ADJ_SUFFIX = re.compile(r"(ful|ous|ic|ive|al|ent|ant|less|able|ible)$")
_TRIPLE = re.compile(r"\b([a-z]+), ([a-z]+),? and ([a-z]+) ([a-z]+)\b", re.I)
_COMMON_ADJ = {
    "grand", "ancient", "majestic", "old", "great", "rich", "serene", "lush", "deep",
    "quiet", "warm", "bright", "dark", "vast", "rare", "pure", "fine", "rare", "proud",
}  # fmt: skip
#: A citation: [3], or several in one bracket the way the model writes them: [1, 17],
#: [7, 11, 12], [3-5], [3–5]. Adjacent brackets ([2][3]) are separate matches.
MARKER = re.compile(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]")
_RANGE_MAX = 10  # a "range" wider than this is two numbers joined by mistake, not a span


def cited(marker: str) -> list[int]:
    """The fact numbers in one marker's inside ("1, 17" or "3-5"), in order, no repeats."""
    out: list[int] = []
    for part in marker.split(","):
        ends = [int(n) for n in re.split(r"\s*[–-]\s*", part.strip())]
        a, b = ends[0], ends[-1]
        span = range(a, b + 1) if 0 <= b - a <= _RANGE_MAX else ends
        out += [n for n in span if n not in out]
    return out


def citations(text: str) -> list[int]:
    """Every fact number cited in text, combined markers expanded."""
    return [n for m in MARKER.finditer(text) for n in cited(m.group(1))]


def words(text: str, lang: str = "en") -> int:
    text = MARKER.sub("", text)
    if lang != "en":  # \w splits Devanagari at its vowel signs; count spaced words
        return sum(1 for t in text.split() if re.search(r"\w", t))
    return len(re.findall(r"[\w’'-]+", text))


def _adjective(word: str) -> bool:
    w = word.lower()
    return w in _COMMON_ADJ or (len(w) > 4 and bool(_ADJ_SUFFIX.search(w)))


def slop(text: str, lang: str = "en") -> list[str]:
    """Every banned phrase or shape found, in a readable form. Empty means clean."""
    low = text.lower()
    lang_found = [p for p in BANNED_LANG.get(lang, []) if p in text]
    # \w* after the stem: "delves" and "boasted" are the same slop as "delve" and "boasts".
    found = [p for p in BANNED if re.search(rf"\b{re.escape(p.removesuffix('s'))}\w*", low)]
    found += [f"whether…or: {m.group(0)!r}" for m in WHETHER.finditer(text)]
    for m in _TRIPLE.finditer(text):
        if all(_adjective(w) for w in m.group(1, 2, 3)):
            found.append(f"stacked adjectives: {m.group(0)!r}")
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for a, b in zip(sentences, sentences[1:], strict=False):
        if a.endswith("?") and b.endswith("?"):
            found.append(f"rhetorical questions in a row: {a!r} {b!r}")
    return found + lang_found


def problems(segments: list[tuple[str, str]], n_facts: int, length_min: int, lang: str = "en") -> list[str]:
    """Everything wrong with a draft. Empty means it can ship."""
    out: list[str] = []
    if not segments:
        return ["no segments"]
    for label, text in segments:
        numbers = citations(text)
        if bad := [n for n in numbers if not 1 <= n <= n_facts]:
            out.append(f"markers point at no fact: {bad}")
        if label in ("history", "disputed") and not numbers:
            out.append(f"uncited {label} segment: {text[:60]!r}")
        if label == "legend" and not legend_told(text, lang):
            out.append(f"legend not told as legend: {text[:60]!r}")
    full = "\n\n".join(t for _, t in segments)
    out += [f"slop: {s}" for s in slop(full, lang)]
    low, high = BANDS[length_min]
    if not low <= (n := words(full, lang)) <= high:
        out.append(f"length {n} words, want {low}-{high} for {length_min} min")
    return out
