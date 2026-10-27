"""Matching what travellers type to corpus names: "story mysuru palace", "मैसूर पैलेस की कहानी".

normalize() folds case, punctuation, filler words ("the", "story of", "की कहानी") and
the common spellings of one place (Mysore/Mysuru, Coorg/Kodagu ...) to one form.
NATIVE maps Hindi and Kannada names of the demo subjects to their corpus names (the
poi table's own name_kn covers Kannada for every Karnataka place). best() is the
difflib fallback: one clear winner at 0.85 or better, or nothing.
"""

from __future__ import annotations

import difflib
import unicodedata
from collections.abc import Iterable

#: Spellings of one place, folded to the first (WA-11, WA-12).
SPELLINGS = {
    "mysore": "mysuru", "bangalore": "bengaluru", "srirangapatnam": "srirangapatna",
    "chamundi": "chamundeshwari", "vitthala": "vittala", "vittal": "vittala", "vithala": "vittala",
    "coorg": "kodagu", "chikmagalur": "chikkamagaluru", "chikmagaluru": "chikkamagaluru",
}  # fmt: skip
#: Words that ask for a story or point at it, never part of a name.
FILLER = [
    "tell me", "story of", "stories of", "story about", "katha of", "the story", "story", "stories",
    "katha", "about", "the", "of", "please",
    "की कहानी", "का किस्सा", "की कथा", "कहानी", "कथा", "के बारे में", "सुनाओ", "बताओ",
    "ಕಥೆ", "ಕತೆ", "ಬಗ್ಗೆ", "ಹೇಳಿ",
]  # fmt: skip
#: Hindi and Kannada names of the six demo subjects (katha_pregenerate.DEMO).
NATIVE = {
    "मैसूर": "Mysuru", "मैसूरु": "Mysuru", "ಮೈಸೂರು": "Mysuru",
    "मैसूर पैलेस": "Mysore Palace", "मैसूर महल": "Mysore Palace", "मैसूर का महल": "Mysore Palace",
    "ಮೈಸೂರು ಅರಮನೆ": "Mysore Palace", "ಅಂಬಾ ವಿಲಾಸ": "Mysore Palace",
    "चामुंडेश्वरी मंदिर": "Chamundeshwari Temple", "चामुंडी मंदिर": "Chamundeshwari Temple",
    "ಚಾಮುಂಡೇಶ್ವರಿ ದೇವಸ್ಥಾನ": "Chamundeshwari Temple", "ಚಾಮುಂಡಿ ಬೆಟ್ಟ": "Chamundeshwari Temple",
    "विट्ठल मंदिर": "Vittala Temple", "विठ्ठल मंदिर": "Vittala Temple", "ವಿಠ್ಠಲ ದೇವಸ್ಥಾನ": "Vittala Temple",
    "हम्पी": "Hampi", "ಹಂಪಿ": "Hampi",
    "देवराज मार्केट": "Devaraja Market", "देवराज बाज़ार": "Devaraja Market", "देवराज बाजार": "Devaraja Market",
    "ದೇವರಾಜ ಮಾರುಕಟ್ಟೆ": "Devaraja Market",
}  # fmt: skip
CUTOFF = 0.85
CLEAR_LEAD = 0.05  # the winner must beat the runner-up by this much


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    # Punctuation and symbols (the danda too) by Unicode category: a regex \W would also
    # take Devanagari and Kannada vowel signs, which are marks, not word characters.
    text = "".join(" " if unicodedata.category(c)[0] in "PS" else c for c in text)
    return " ".join(text.split())


_FILLER = [_fold(f) for f in sorted(FILLER, key=len, reverse=True)]
_NATIVE = {_fold(k): v for k, v in NATIVE.items()}


def normalize(text: str) -> str:
    """One form per name: folded, fillers out, spellings unified, native names in English."""
    t = f" {_fold(text)} "
    for f in _FILLER:
        t = t.replace(f" {f} ", " ")
    t = " ".join(t.split())
    if t in _NATIVE:
        t = _fold(_NATIVE[t])
    return " ".join(SPELLINGS.get(w, w) for w in t.split())


def best(query: str, names: Iterable[str]) -> str | None:
    """The one name close enough to query (normalized forms, ratio >= CUTOFF) with a clear
    lead over the next; None when nothing is close or two are."""
    q = normalize(query)
    forms: dict[str, str] = {}  # "mysore" and "mysuru" are one candidate, not a tie
    for n in names:
        forms.setdefault(normalize(n), n)
    scored = sorted(((difflib.SequenceMatcher(None, q, f).ratio(), n) for f, n in forms.items()),
                    reverse=True)  # fmt: skip
    if not scored or scored[0][0] < CUTOFF:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < CLEAR_LEAD:
        return None
    return scored[0][1]
