"""Katha checks from design/katha-style.md: slop, citations, labels and length.

Pure functions over (label, text) segments. A story that fails is regenerated,
never shipped. Grow BANNED when the taste gate finds more.
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

#: Read-aloud budgets (rule 10): about 300, 750 and 1,500 words.
BANDS = {2: (220, 400), 5: (580, 950), 10: (1150, 1850)}

#: Rule 9: a legend is told as a legend.
LEGEND_CUES = re.compile(
    r"people (here )?say|legend|the story goes|it is said|they say|is told|tell[s]? (of|how)"
    r"|according to (tradition|the story|local belief)|believe[sd]?|myth|tradition holds",
    re.I,
)

#: Adjectives that turn up in stacked triples ("grand, ancient and majestic").
# Evaluative suffixes only: "carved, painted and gilded pillars" is concrete, not slop.
_ADJ_SUFFIX = re.compile(r"(ful|ous|ic|ive|al|ent|ant|less|able|ible)$")
_TRIPLE = re.compile(r"\b([a-z]+), ([a-z]+),? and ([a-z]+) ([a-z]+)\b", re.I)
_COMMON_ADJ = {
    "grand", "ancient", "majestic", "old", "great", "rich", "serene", "lush", "deep",
    "quiet", "warm", "bright", "dark", "vast", "rare", "pure", "fine", "rare", "proud",
}  # fmt: skip
MARKER = re.compile(r"\[(\d+)\]")


def words(text: str) -> int:
    return len(re.findall(r"[\w’'-]+", MARKER.sub("", text)))


def _adjective(word: str) -> bool:
    w = word.lower()
    return w in _COMMON_ADJ or (len(w) > 4 and bool(_ADJ_SUFFIX.search(w)))


def slop(text: str) -> list[str]:
    """Every banned phrase or shape found, in a readable form. Empty means clean."""
    low = text.lower()
    found = [p for p in BANNED if re.search(rf"\b{re.escape(p)}\b", low)]
    found += [f"whether…or: {m.group(0)!r}" for m in WHETHER.finditer(text)]
    for m in _TRIPLE.finditer(text):
        if all(_adjective(w) for w in m.group(1, 2, 3)):
            found.append(f"stacked adjectives: {m.group(0)!r}")
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for a, b in zip(sentences, sentences[1:], strict=False):
        if a.endswith("?") and b.endswith("?"):
            found.append(f"rhetorical questions in a row: {a!r} {b!r}")
    return found


def problems(segments: list[tuple[str, str]], n_facts: int, length_min: int) -> list[str]:
    """Everything wrong with a draft. Empty means it can ship."""
    out: list[str] = []
    if not segments:
        return ["no segments"]
    for label, text in segments:
        cited = [int(n) for n in MARKER.findall(text)]
        if bad := [n for n in cited if not 1 <= n <= n_facts]:
            out.append(f"markers point at no fact: {bad}")
        if label in ("history", "disputed") and not cited:
            out.append(f"uncited {label} segment: {text[:60]!r}")
        if label == "legend" and not LEGEND_CUES.search(text):
            out.append(f"legend not told as legend: {text[:60]!r}")
    full = "\n\n".join(t for _, t in segments)
    out += [f"slop: {s}" for s in slop(full)]
    low, high = BANDS[length_min]
    if not low <= (n := words(full)) <= high:
        out.append(f"length {n} words, want {low}-{high} for {length_min} min")
    return out
