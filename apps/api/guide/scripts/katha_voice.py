"""Read Katha stories aloud into the audio bucket (V3-AF), and report the voices.

    cd apps/api && TY_API_URL=https://... KATHA_AUDIO_BUCKET=... KATHA_AUDIO_BASE_URL=... \\
        uv run python -m guide.scripts.katha_voice [--budget 200000] [--voices-only] \\
        [place:Mysore Palace:2:en ...]

Stories come from the deployed API (POST /guide/katha), so a cached story costs no
model call; a story the cache lacks is written there first. Each is read once per
language, chapter by chapter, through guide.katha.voice; audio already stored is
skipped. Every character is counted against --budget before the call.

Writes data/katha/audio/voices.json (every voice per language and the one chosen)
and appends data/katha/audio/calls.log (story, language, voice, characters).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime

from guide.katha import voice as v
from guide.retrieval.seed import DATA
from ty_contracts import KathaStory

OUT = DATA / "katha" / "audio"
#: The demo trip's four English stories (Mysuru, cached by pre-generation) and the
#: Mysore Palace 2-minute Hindi.
DEMO = ["place:Mysore Palace:2:en", "place:Mysore Palace:5:en", "city:Mysuru:2:en", "city:Mysuru:5:en",
        "place:Mysore Palace:2:hi"]  # fmt: skip


def fetch_story(api: str, kind: str, subject: str, length: int, lang: str) -> KathaStory:
    body = json.dumps({"subject_kind": kind, "subject": subject, "length_min": length, "lang": lang}).encode()
    req = urllib.request.Request(f"{api.rstrip('/')}/guide/katha", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})  # fmt: skip
    with urllib.request.urlopen(req, timeout=300) as r:
        return KathaStory.model_validate_json(r.read())


def voice_report(http: v.Http) -> dict:
    report = {}
    for lang in v.LANG_CODE:
        names = v.voices(http, lang)
        report[lang] = {"chosen": v.pick_voice(names), "voices": names}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "voices.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stories", nargs="*", default=DEMO)
    p.add_argument("--budget", type=int, default=200_000)
    p.add_argument("--voices-only", action="store_true")
    args = p.parse_args()
    http = v.adc_http()
    report = voice_report(http)
    for lang, r in report.items():
        print(f"{lang}: {r['chosen']} ({len(r['voices'])} voices)")
    if args.voices_only:
        return
    storage = v.GcsStorage(os.environ["KATHA_AUDIO_BUCKET"], http, os.environ.get("KATHA_AUDIO_BASE_URL"))
    budget = v.Budget(args.budget)
    api = os.environ["TY_API_URL"]
    skipped = run(args.stories, lambda *a: fetch_story(api, *a), report, http, storage, budget)
    print(f"TTS characters this run: {budget.used} (budget {budget.limit}); skipped {skipped}")
    if skipped:
        sys.exit(1)


def run(specs, fetch, report: dict, http: v.Http, storage: v.Storage, budget: v.Budget) -> int:
    """Read each spec aloud; a story the API can't give (503: it failed its checks twice;
    404; a timeout) or TTS can't read is skipped and the rest go on. Returns the number
    skipped. The budget is one counter for the whole run, so the cap holds."""
    skipped = 0
    for spec in specs:
        kind, subject, length, lang = spec.split(":")
        try:
            story = fetch(kind, subject, int(length), lang)
        except urllib.error.HTTPError as e:
            print(f"SKIPPED {spec}: HTTP {e.code}")
            skipped += 1
            continue
        except OSError as e:
            print(f"SKIPPED {spec}: {type(e).__name__}")
            skipped += 1
            continue
        chosen = report[story.lang]["chosen"]
        try:
            audio, sent = v.read_aloud(story, chosen, http, storage, budget)
        except v.BudgetSpent as e:
            print(f"stop: {e}")
            return skipped + 1
        except RuntimeError as e:  # TTS or upload failed: a re-run resumes from the stored chapters
            print(f"FAILED {spec}: {e}")
            skipped += 1
            continue
        line = f"{story.subject} {story.length_min}min {story.lang} {chosen} {len(audio)} chapters {sent} chars"
        print(line)
        with (OUT / "calls.log").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}\t{line}\n")
    return skipped


if __name__ == "__main__":
    main()
