"""Check TY4's web strings (apps/web/lib/i18n) against the phrasebook's rules and terms.

    cd services/translate && uv run python scripts/review_web_strings.py [out.md]

Reads screens-plan.json, screens-guide.json and the EXTRA table in index.tsx (read only; TY4
owns them). Flags per string and language: missing, untranslated (same as English), wrong
script, length, foreign punctuation, a lost {placeholder} or number, and a travel term whose
phrasebook word is absent (e.g. "trip" without यात्रा). Flags are leads for the native
speakers, not verdicts.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.checks import check

WEB = Path(__file__).resolve().parents[3] / "apps/web/lib/i18n"
LANGS = ["hi", "kn", "ta", "te", "bn"]
PLACEHOLDER = re.compile(r"\{\w+\}")
NUMBER = re.compile(r"\d+")  # \d matches Bengali digits too; int("১৫") == 15
# Names and acronyms that stay in Latin script by design; ignored by the script check.
LATIN_OK = re.compile(r"Travel Yantra|OpenStreetMap|IRCTC|PNR|DELETE|\bAI\b|\bUPI\b|\bOTP\b")

# The phrasebook's word for each travel term (services/translate/app/phrasebook.tsv), as stems
# so that inflected forms match (பயணத்தை, ಪ್ರವಾಸವನ್ನು).
TERMS: dict[str, dict[str, list[str]]] = {
    "trip": {
        "hi": ["यात्रा"],
        "kn": ["ಪ್ರವಾಸ"],
        "ta": ["பயண"],
        "te": ["ప్రయాణ"],
        "bn": ["ভ্রমণ"],
    },
    "story": {
        "hi": ["कहानी", "कहानि", "कथा"],
        "kn": ["ಕಥೆ"],
        "ta": ["கதை"],
        "te": ["కథ"],
        "bn": ["গল্প", "কাহিনী", "কাহিনি"],
    },
    "day": {
        "hi": ["दिन"],
        "kn": ["ದಿನ"],
        "ta": ["நாள்", "நாட்க", "நாளை", "நாளி", "நாளு"],
        "te": ["రోజు", "రోజుల"],
        "bn": ["দিন"],
    },
    "train": {
        "hi": ["ट्रेन"],
        "kn": ["ರೈಲು", "ರೈಲಿ"],
        "ta": ["ரயில்"],
        "te": ["రైలు", "రైళ్ల"],
        "bn": ["ট্রেন"],
    },
    "bus": {
        "hi": ["बस"],
        "kn": ["ಬಸ್"],
        "ta": ["பேருந்து", "பஸ்"],
        "te": ["బస్సు", "బస్"],
        "bn": ["বাস"],
    },
    "flight": {
        "hi": ["उड़ान", "फ़्लाइट", "फ्लाइट"],
        "kn": ["ವಿಮಾನ"],
        "ta": ["விமான"],
        "te": ["విమాన"],
        "bn": ["ফ্লাইট", "বিমান"],
    },
    "budget": {
        "hi": ["बजट"],
        "kn": ["ಬಜೆಟ್"],
        "ta": ["பட்ஜெட்"],
        "te": ["బడ్జెట్"],
        "bn": ["বাজেট"],
    },
}
TERM_RE = {
    "trip": r"\btrips?\b",
    "story": r"\bstor(?:y|ies)\b",
    "day": r"\bdays?\b",
    "train": r"\btrains?\b",
    "bus": r"\bbus(?:es)?\b",
    "flight": r"\bflights?\b",
    "budget": r"\bbudget\b",
}
# "Katha" (the product): कथा in Hindi; the word for story elsewhere. Bengali কথা means "talk".
KATHA = {
    "hi": ["कथा"],
    "kn": ["ಕಥೆ", "ಕಥಾ"],
    "ta": ["கதை", "கதா"],
    "te": ["కథ"],
    "bn": ["গল্প", "কাহিনি", "কাহিনী"],
}


def extra_table(tsx: str) -> dict[str, dict[str, str]]:
    """The EXTRA object in index.tsx: `Key: { hi: "…", … },` or `"Key": { … },` lines."""
    block = tsx.split("const EXTRA", 1)[1].split("};", 1)[0]
    out = {}
    for m in re.finditer(r'^\s*(?:"([^"]+)"|(\w+)):\s*\{(.*)\},?\s*$', block, re.MULTILINE):
        out[m[1] or m[2]] = dict(re.findall(r'(\w\w):\s*"([^"]*)"', m[3]))
    return out


def load() -> dict[str, tuple[str, dict[str, str]]]:
    """English -> (file, {lang: text})."""
    out: dict[str, tuple[str, dict[str, str]]] = {}
    for name in ("screens-plan.json", "screens-guide.json"):
        for en, tr in json.loads((WEB / name).read_text(encoding="utf-8")).items():
            out[en] = (name, tr)
    for en, tr in extra_table((WEB / "index.tsx").read_text(encoding="utf-8")).items():
        out[en] = ("index.tsx EXTRA", tr)
    return out


def flags(en: str, lang: str, out: str | None) -> list[str]:
    if not out:
        return ["missing"]
    words = PLACEHOLDER.sub("", en)
    found = check(en, out, lang, script_text=LATIN_OK.sub("", PLACEHOLDER.sub("", out)))
    if out.strip() == en.strip() and re.search(r"[A-Za-z]{3}", words):
        found.append("untranslated")
    if sorted(PLACEHOLDER.findall(en)) != sorted(PLACEHOLDER.findall(out)):
        found.append("placeholder")
    if sorted(map(int, NUMBER.findall(en))) != sorted(map(int, NUMBER.findall(out))):
        found.append("number")
    for term, pattern in TERM_RE.items():
        if re.search(pattern, words, re.IGNORECASE) and not any(
            w in out for w in TERMS[term][lang]
        ):
            found.append(f"term:{term}")
    if re.search(r"\bkatha\b", words, re.IGNORECASE) and not any(w in out for w in KATHA[lang]):
        found.append("term:katha")
    return found


def review() -> tuple[int, list[tuple[str, str, str, str, list[str]]]]:
    strings = load()
    rows = []
    for en, (src, tr) in strings.items():
        for lang in LANGS:
            if f := flags(en, lang, tr.get(lang)):
                rows.append((src, en, lang, tr.get(lang, ""), f))
    return len(strings), rows


def _cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def markdown(total: int, rows: list) -> str:
    lines = [
        "| File | English | Lang | Text | Flags |",
        "| --- | --- | --- | --- | --- |",
    ]
    for src, en, lang, out, f in rows:
        lines.append(f"| {src} | {_cell(en)} | {lang} | {_cell(out)} | {', '.join(f)} |")
    head = f"{total} strings × {len(LANGS)} languages checked; {len(rows)} flagged.\n\n"
    return head + "\n".join(lines) + "\n"


if __name__ == "__main__":
    total, rows = review()
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(markdown(total, rows), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{total} strings, {len(rows)} flagged")
