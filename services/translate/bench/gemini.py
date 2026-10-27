"""Gemini side of the P2 comparison (host, Vertex via ADC). Few calls, every result cached to disk.

usage: python gemini.py translate   -> gemini_tr.json   (5 calls: one per language, 10 answers each)
       python gemini.py judge       -> judge.json       (10 calls: one per language per system)
       python gemini.py qa          -> qa.md / qa.json  (no calls: run_qa on cached results)
"""

import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "results"
sys.path.insert(0, str(HERE.parent))  # services/translate, for app.qa
DATA = json.loads((HERE / "answers.json").read_text(encoding="utf-8"))
LANGS = {"hi": "Hindi", "kn": "Kannada", "ta": "Tamil", "te": "Telugu", "bn": "Bengali"}
FLASH = os.environ.get("TY_MODEL_FLASH", "gemini-3.5-flash")
LITE = os.environ.get("TY_MODEL_LITE", "gemini-3.1-flash-lite")
CALLS = OUT / "calls.log"


def client():
    from google import genai

    return genai.Client(location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"))


def ask_json(c, model, prompt):
    from google.genai import errors, types

    config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0)
    for attempt in range(4):  # the trial quota 429s quickly: wait 20, 40, 60 s
        t = time.perf_counter()
        try:
            r = c.models.generate_content(model=model, contents=prompt, config=config)
            break
        except errors.ClientError as e:
            with CALLS.open("a", encoding="utf-8") as f:
                f.write(f"{model}\t{time.perf_counter() - t:.2f}s\tHTTP {e.code}\n")
            if e.code != 429 or attempt == 3:
                raise
            time.sleep(20 * (attempt + 1))
    dt = time.perf_counter() - t
    u = r.usage_metadata
    with CALLS.open("a", encoding="utf-8") as f:
        f.write(f"{model}\t{dt:.2f}s\tin={u.prompt_token_count}\tout={u.candidates_token_count}\n")
    return json.loads(r.text), dt


def translate():
    c, out, times = client(), {}, {}
    for lang, name in LANGS.items():
        prompt = (
            f"Translate each English string in this JSON array into {name}. Keep every [n] marker "
            f"exactly as written. Keep these place names in Latin script, unchanged: "
            f"{', '.join(DATA['entities'])}. Return only a JSON array of {len(DATA['answers'])} "
            f"strings in the same order.\n\n{json.dumps(DATA['answers'], ensure_ascii=False)}"
        )
        out[lang], times[lang] = ask_json(c, LITE, prompt)
    (OUT / "gemini_tr.json").write_text(
        json.dumps(
            {"model": LITE, "seconds_per_10": times, "translations": out},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print({k: round(v, 2) for k, v in times.items()})


def back():
    c = client()
    gem = json.loads((OUT / "gemini_tr.json").read_text(encoding="utf-8"))["translations"]
    out = {"gemini": {}}
    for lang, name in LANGS.items():
        prompt = (
            f"Translate each {name} string in this JSON array into English, literally. Return only "
            f"a JSON array of {len(gem[lang])} strings in the same order.\n\n"
            f"{json.dumps(gem[lang], ensure_ascii=False)}"
        )
        out["gemini"][lang], _ = ask_json(c, LITE, prompt)
    (OUT / "back.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("back-translated", list(out["gemini"]))


def systems():
    found = {}
    if (OUT / "it2_forward.json").exists():
        found["indictrans2"] = json.loads((OUT / "it2_forward.json").read_text(encoding="utf-8"))[
            "translations"
        ]
    found["gemini"] = json.loads((OUT / "gemini_tr.json").read_text(encoding="utf-8"))[
        "translations"
    ]
    found["gemini+norm"] = {k: [normalise(t, k) for t in v] for k, v in found["gemini"].items()}
    return found


def normalise(text: str, lang: str) -> str:
    """The post-process a Gemini translator would need: danda for a stray pipe or CJK stop."""
    stop = "।" if lang in ("hi", "bn") else "."
    return re.sub(r"\s*[|。]\s*$", stop, text).replace("。", stop)


def judge():
    c = client()
    scores = {}
    for system, by in systems().items():
        for lang, name in LANGS.items():
            pairs = [{"en": s, "out": o} for s, o in zip(DATA["answers"], by[lang])]
            prompt = (
                f"You grade {name} translations of English travel-guide sentences. For each pair, "
                "score adequacy 1-5 (5 = all meaning kept, natural; 3 = meaning mostly kept; "
                "1 = wrong). Place names may stay in Latin script. Return only a JSON array of "
                f"{len(pairs)} integers.\n\n{json.dumps(pairs, ensure_ascii=False)}"
            )
            scores[f"{system}/{lang}"], _ = ask_json(c, FLASH, prompt)
    (OUT / "judge.json").write_text(
        json.dumps({"model": FLASH, "scores": scores}, indent=1), encoding="utf-8"
    )
    print(scores)


def qa():
    from app.qa import report, report_markdown, run_qa

    back = json.loads((OUT / "back.json").read_text(encoding="utf-8"))
    judged = json.loads((OUT / "judge.json").read_text(encoding="utf-8"))["scores"]
    md, js = [], {}
    for system, by in systems().items():
        base = system.split("+")[0]  # gemini+norm reuses gemini's back-translations and scores

        class Back:
            def translate_to_en(self, texts, source, _s=base):
                return back[_s][source]

        results = []
        for lang in LANGS:
            sc = iter(judged[f"{base}/{lang}"])

            class Judge:
                def score(self, src, out, lang, _sc=sc):
                    return int(next(_sc))

            pairs = list(zip(DATA["answers"], by[lang]))
            results += run_qa(pairs, lang, Back(), Judge(), entities=DATA["entities"])
        js[system] = report(results)
        md.append(f"### {system}\n\n" + report_markdown(results))
        js[system + "_examples"] = [
            {"lang": r.lang, "out": r.out, "chrf": r.chrf, "adequacy": r.adequacy, "flags": r.flags}
            for r in results
            if r.flags
        ][:10]
    (OUT / "qa.md").write_text("\n".join(md), encoding="utf-8")
    (OUT / "qa.json").write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    {"translate": translate, "back": back, "judge": judge, "qa": qa}[sys.argv[1]]()
