"""Language QA on every translated output, plus a per-language report (JSON and Markdown).

Checks: back-translation chrF against the source, entity presence, script, length ratio, and an
LLM adequacy score (1-5). Back-translator and judge are injected, so tests use fakes and the
service decides which real models to wire in. A failing output falls back to the English source.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Protocol

from . import checks


class BackTranslator(Protocol):
    def translate_to_en(self, texts: list[str], source: str) -> list[str]: ...


class Judge(Protocol):
    def score(self, src: str, out: str, lang: str) -> int: ...  # adequacy 1-5


@dataclass(frozen=True)
class Thresholds:
    min_chrf: float = 0.35
    min_adequacy: int = 3


DEFAULT = Thresholds()


@dataclass
class QAResult:
    lang: str
    src: str
    out: str  # text to ship: the translation, or the English source after a fallback
    chrf: float
    adequacy: int
    flags: list[str] = field(default_factory=list)

    @property
    def fell_back(self) -> bool:
        return "fallback_en" in self.flags


def chrf(ref: str, hyp: str, n: int = 6, beta: float = 2.0) -> float:
    """Character n-gram F-score (chrF), 0..1, averaged over n-gram orders 1..n."""

    def grams(s: str, k: int) -> Counter[str]:
        s = "".join(s.split())
        return Counter(s[i : i + k] for i in range(len(s) - k + 1))

    scores = []
    for k in range(1, n + 1):
        r, h = grams(ref, k), grams(hyp, k)
        hit = sum((r & h).values())
        if not r or not h or not hit:
            scores.append(0.0)
            continue
        p, rc = hit / sum(h.values()), hit / sum(r.values())
        scores.append((1 + beta**2) * p * rc / (beta**2 * p + rc))
    return sum(scores) / n


def entity_flags(src: str, out: str, entities: list[str], names: dict, lang: str) -> list[str]:
    return [
        f"entity_lost:{e}"
        for e in entities
        if e in src and e not in out and names.get(e, {}).get(lang, e) not in out
    ]


class Judged:
    """Judge wrapper that never scores the same (src, out, lang) twice."""

    def __init__(self, judge: Judge) -> None:
        self._judge, self._seen = judge, {}

    def score(self, src: str, out: str, lang: str) -> int:
        key = (src, out, lang)
        if key not in self._seen:
            self._seen[key] = self._judge.score(src, out, lang)
        return self._seen[key]


def run_qa(
    pairs: list[tuple[str, str]],
    lang: str,
    back: BackTranslator,
    judge: Judge,
    entities: list[str] | None = None,
    names: dict[str, dict[str, str]] | None = None,
    th: Thresholds = DEFAULT,
) -> list[QAResult]:
    """QA every (source, translation) pair. Failures are flagged and fall back to the source."""
    entities, names = entities or [], names or {}
    backs = back.translate_to_en([o for _, o in pairs], lang) if pairs else []
    results = []
    for (src, out), bt in zip(pairs, backs):
        score = chrf(src, bt)
        adequacy = judge.score(src, out, lang)
        flags = checks.check(src, out, lang) + entity_flags(src, out, entities, names, lang)
        if score < th.min_chrf:
            flags.append("low_backtranslation")
        if adequacy < th.min_adequacy:
            flags.append("low_adequacy")
        if flags:
            flags.append("fallback_en")
        results.append(QAResult(lang, src, src if flags else out, round(score, 3), adequacy, flags))
    return results


def report(results: list[QAResult]) -> dict:
    """Per-language accuracy: pass rate, mean chrF, mean adequacy, flag counts."""
    by_lang: dict[str, list[QAResult]] = defaultdict(list)
    for r in results:
        by_lang[r.lang].append(r)
    out = {}
    for lang, rs in sorted(by_lang.items()):
        n = len(rs)
        out[lang] = {
            "n": n,
            "pass_rate": round(sum(not r.flags for r in rs) / n, 3),
            "mean_chrf": round(sum(r.chrf for r in rs) / n, 3),
            "mean_adequacy": round(sum(r.adequacy for r in rs) / n, 2),
            "flags": dict(Counter(f.split(":")[0] for r in rs for f in r.flags)),
        }
    return out


def report_json(results: list[QAResult]) -> str:
    return json.dumps(report(results), indent=2, ensure_ascii=False)


def report_markdown(results: list[QAResult]) -> str:
    rows = ["| Language | N | Pass rate | chrF | Adequacy | Flags |", "|---|---|---|---|---|---|"]
    for lang, s in report(results).items():
        flags = ", ".join(f"{k}: {v}" for k, v in s["flags"].items()) or "none"
        rows.append(
            f"| {lang} | {s['n']} | {s['pass_rate']:.0%} | {s['mean_chrf']} "
            f"| {s['mean_adequacy']} | {flags} |"
        )
    return "\n".join(rows) + "\n"
