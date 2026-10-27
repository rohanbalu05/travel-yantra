"""P3 bench: real /guide/ask answers through the real translate path, then run_qa.

The translate service must be running locally with TY_TRANSLATOR=gemini and TY_MAX_BATCH=64
(one Gemini call per language). Back-translation and the judge are Gemini calls here, logged in
results/calls.log like gemini.py.

usage: python real_path.py <answers.json> [translate_url]   ->  results/real_*.json, real_qa.md
"""

import json
import re
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
OUT = HERE / "results"
sys.path.insert(0, str(HERE.parent))  # services/translate, for app.qa
sys.path.insert(0, str(HERE))
import gemini

from app.qa import report, report_markdown, run_qa

MARKER = re.compile(r"\[\d+\]")
SENTENCE = re.compile(r"(?<=[.!?])\s+")
LANGS = gemini.LANGS


def sentences(answers: list[dict]) -> list[str]:
    """Each answer's text split into sentences, as the bot sends long text."""
    return [
        s
        for a in answers
        for line in a["text"].split("\n")
        for s in SENTENCE.split(line)
        if s.strip()
    ]


def translate(texts: list[str], url: str) -> dict:
    out = {}
    markers = sorted({m for t in texts for m in MARKER.findall(t)})
    with httpx.Client(timeout=180) as client:
        for lang in LANGS:
            r = client.post(
                f"{url}/translate", json={"texts": texts, "target": lang, "entities": markers}
            )
            r.raise_for_status()
            out[lang] = r.json()
    return out


def main(answers_path: str, url: str = "http://localhost:8768") -> None:
    answers = json.loads(Path(answers_path).read_text(encoding="utf-8"))
    texts = sentences(answers)
    saved = OUT / "real_translations.json"
    if saved.exists():  # resume: the translate step already ran; only QA is left
        tr = json.loads(saved.read_text(encoding="utf-8"))
    else:
        tr = translate(texts, url)
        saved.write_text(json.dumps(tr, ensure_ascii=False, indent=1), encoding="utf-8")
    service_pass = {
        lang: round(sum(not f for f in d["flags"]) / len(texts), 3) for lang, d in tr.items()
    }
    c = gemini.client()
    cache_path = OUT / "real_qa_calls.json"  # per language, so a 429 never repeats a done call
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    results = []
    for lang, name in LANGS.items():
        outs = tr[lang]["translations"]
        if lang not in cache:
            back, _ = gemini.ask_json(
                c,
                gemini.LITE,
                f"Translate each {name} string in this JSON array into English, literally. Return "
                f"only a JSON array of {len(outs)} strings in the same order.\n\n"
                f"{json.dumps(outs, ensure_ascii=False)}",
            )
            pairs = [{"en": s, "out": o} for s, o in zip(texts, outs)]
            time.sleep(5)
            scores, _ = gemini.ask_json(
                c,
                gemini.FLASH,
                f"You grade {name} translations of English travel-guide sentences. For each pair, "
                "score adequacy 1-5 (5 = all meaning kept, natural; 3 = meaning mostly kept; "
                f"1 = wrong). Return only a JSON array of {len(pairs)} integers.\n\n"
                f"{json.dumps(pairs, ensure_ascii=False)}",
            )
            cache[lang] = {"back": back, "scores": scores}
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
            time.sleep(5)
        back, scores = cache[lang]["back"], cache[lang]["scores"]

        class Back:
            def translate_to_en(self, t, source, _b=back):
                return _b

        it = iter(scores)

        class Judge:
            def score(self, src, out, lang, _s=it):
                return int(next(_s))

        results += run_qa(list(zip(texts, outs)), lang, Back(), Judge())
    summary = {
        "sentences": len(texts),
        "service_flags_pass": service_pass,
        "run_qa": report(results),
    }
    (OUT / "real_qa.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    md = report_markdown(results)
    (OUT / "real_qa.md").write_text(md, encoding="utf-8")
    print(json.dumps({"sentences": len(texts), "service_flags_pass": service_pass}), "\n" + md)


if __name__ == "__main__":
    main(*sys.argv[1:])
