"""IndicTrans2 CPU bench, run inside the ty-translate image (production code path).

usage: python bench_it2.py forward <out.json>     time + translate answers.json into 5 languages
       python bench_it2.py back <in.json> <out.json>  back-translate {system: {lang: [texts]}} to English
"""

import json
import re
import resource
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, "/srv")
from app.service import TranslationService
from app.translator import LANGS, IndicTrans2Translator

DATA = json.loads(Path("/bench/answers.json").read_text(encoding="utf-8"))
MARKER = re.compile(r"\[\d+\]")


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def forward(out_path: str) -> None:
    t0 = time.perf_counter()
    tr = IndicTrans2Translator()
    load_s = time.perf_counter() - t0
    rss_load = rss_mb()
    answers = DATA["answers"]
    ents = sorted({m for a in answers for m in MARKER.findall(a)}) + DATA["entities"]
    single, batch, outs, flags = {}, {}, {}, {}
    for lang in LANGS:
        times = []
        for a in answers:  # one sentence per request, cache off
            svc = TranslationService(tr, cache_size=0)
            t = time.perf_counter()
            svc.translate_checked([a], lang, entities=ents)
            times.append(time.perf_counter() - t)
        single[lang] = times
        svc = TranslationService(tr, cache_size=0)
        t = time.perf_counter()
        res = svc.translate_checked(answers, lang, entities=ents)
        batch[lang] = time.perf_counter() - t
        outs[lang] = [r.text for r in res]
        flags[lang] = [r.flags for r in res]
    allt = sorted(x for v in single.values() for x in v)
    report = {
        "load_s": round(load_s, 1),
        "rss_after_load_mb": round(rss_load),
        "rss_peak_mb": round(rss_mb()),
        "per_sentence_s": {
            "median": round(statistics.median(allt), 2),
            "p90": round(allt[int(0.9 * len(allt)) - 1], 2),
            "max": round(allt[-1], 2),
            "by_lang_median": {k: round(statistics.median(v), 2) for k, v in single.items()},
        },
        "batch10_s": {k: round(v, 2) for k, v in batch.items()},
        "translations": outs,
        "service_flags": flags,
    }
    Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("translations", "service_flags")}))


class Back:
    """indic-en IndicTrans2 for back-translation (QA)."""

    def __init__(self) -> None:
        self.tr = IndicTrans2Translator("ai4bharat/indictrans2-indic-en-dist-200M")

    def to_en(self, texts: list[str], lang: str) -> list[str]:
        out = []
        for i in range(0, len(texts), 8):
            out += self.tr.translate(texts[i : i + 8], target="en", source=lang)
        return out


def back(in_path: str, out_path: str) -> None:
    data = json.loads(Path(in_path).read_text(encoding="utf-8"))
    b = Back()
    res = {sysname: {lang: b.to_en(texts, lang) for lang, texts in by.items()} for sysname, by in data.items()}
    Path(out_path).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("back-translated", {s: list(v) for s, v in res.items()})


if __name__ == "__main__":
    {"forward": forward, "back": back}[sys.argv[1]](*sys.argv[2:])
