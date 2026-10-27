"""Entity protection and output checks (script, length). Flags are short strings."""

from __future__ import annotations

import re

SCRIPT_RANGES: dict[str, tuple[int, int]] = {
    "hi": (0x0900, 0x097F),
    "bn": (0x0980, 0x09FF),
    "ta": (0x0B80, 0x0BFF),
    "te": (0x0C00, 0x0C7F),
    "kn": (0x0C80, 0x0CFF),
}

MIN_SCRIPT_RATIO = 0.6  # share of letters that must be in the target script
MIN_LEN_RATIO, MAX_LEN_RATIO = 0.3, 4.0  # output chars / input chars


def _placeholder(i: int) -> str:
    return f"XQ{i}Z"


def protect(text: str, entities: list[str]) -> tuple[str, dict[str, str]]:
    """Swap entity names for placeholders so the model cannot translate them.

    Longest names first, so "Mysuru Palace" wins over "Mysuru".
    """
    slots: dict[str, str] = {}
    for i, name in enumerate(sorted(set(entities), key=len, reverse=True)):
        pat = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)") if name else None
        if pat and pat.search(text):
            ph = _placeholder(i)
            text = pat.sub(ph, text)
            slots[ph] = name
    return text, slots


def restore(
    text: str, slots: dict[str, str], names: dict[str, dict[str, str]], target: str
) -> tuple[str, list[str]]:
    """Put native (Wikidata) names back; fall back to the original spelling.

    Returns the text and an `entity_lost:<name>` flag for each placeholder the model dropped.
    """
    flags = []
    for ph, name in slots.items():
        if ph not in text:
            flags.append(f"entity_lost:{name}")
            continue
        text = text.replace(ph, names.get(name, {}).get(target, name))
    return text, flags


def script_ok(text: str, target: str) -> bool:
    lo, hi = SCRIPT_RANGES[target]
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    return sum(lo <= ord(c) <= hi for c in letters) / len(letters) >= MIN_SCRIPT_RATIO


def length_ok(src: str, out: str) -> bool:
    if not src.strip():
        return True
    return MIN_LEN_RATIO <= len(out) / len(src) <= MAX_LEN_RATIO


# CJK and full-width punctuation, or a pipe standing in for the danda: never right in our output.
FOREIGN_PUNCT = re.compile(r"[\u3000-\u303f\uff00-\uffef]|\s\|\s*$")


def punctuation_ok(text: str) -> bool:
    return not FOREIGN_PUNCT.search(text)


def check(src: str, out: str, target: str, script_text: str | None = None) -> list[str]:
    """Length uses `out`; the script check uses `script_text` (default `out`)."""
    flags = []
    if not script_ok(out if script_text is None else script_text, target):
        flags.append("wrong_script")
    if not length_ok(src, out):
        flags.append("length")
    if not punctuation_ok(out):
        flags.append("punctuation")
    return flags
