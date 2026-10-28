"""On-demand Katha audio (HQ P7): a story with no audio is read aloud, a chapter a request.

Cloud Run gives an instance CPU only while it serves a request, so work left running
after a response is not reliable. Instead the first request for a story without audio
files a job and answers "pending" at once; each later request for it (clients poll the
same POST /guide/katha) reads the next chapter inline, answers "pending" until the last
and then "ready" with the audio. A job row with a short claim keeps two instances from
reading the same chapter.

Characters are held under KATHA_TTS_DAILY_CHARS a day across every instance (Postgres
katha_tts_usage), checked before each TTS call. Unset or 0: no on-demand audio.
Needs KATHA_AUDIO_BUCKET and KATHA_AUDIO_BASE_URL, as the read path does.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Literal

from ty_contracts import KathaAudio, KathaStory

from ..retrieval.seed import DATA
from . import voice as v

log = logging.getLogger(__name__)

CLAIM_S = 120  # one chapter's TTS and upload; a crashed claim frees itself after this
Status = Literal["ready", "pending", "none"]


def daily_cap() -> int:
    try:
        return max(int(os.environ.get("KATHA_TTS_DAILY_CHARS", "0")), 0)
    except ValueError:
        return 0


def enabled() -> bool:
    return bool(os.environ.get("KATHA_AUDIO_BUCKET") and os.environ.get("KATHA_AUDIO_BASE_URL") and daily_cap())


@lru_cache(maxsize=1)
def chosen_voices() -> dict[str, str]:
    """Language -> the narrator the voice report chose (data/katha/audio/voices.json)."""
    path = DATA / "katha" / "audio" / "voices.json"
    if not path.exists():
        return {}
    return {lang: r["chosen"] for lang, r in json.loads(path.read_text(encoding="utf-8")).items() if r.get("chosen")}


class DailyBudget(v.Budget):
    """v.Budget over today's row in katha_tts_usage: a take that would pass the cap fails
    before the call, whichever instance asks."""

    def __init__(self, db: Any, cap: int):
        super().__init__(cap)
        self.db = db

    def take(self, n: int) -> None:
        row = None
        if n <= self.limit:
            row = self.db.execute(
                "INSERT INTO katha_tts_usage (day, chars) VALUES (current_date, %s) "
                "ON CONFLICT (day) DO UPDATE SET chars = katha_tts_usage.chars + excluded.chars "
                "WHERE katha_tts_usage.chars + excluded.chars <= %s RETURNING chars",
                (n, self.limit),
            ).fetchone()
        if not row:
            raise v.BudgetSpent(f"TTS daily cap {self.limit}: {n} more characters would pass it")
        self.used += n


def _storage(http: v.Http) -> v.Storage:
    return v.GcsStorage(os.environ["KATHA_AUDIO_BUCKET"], http, os.environ["KATHA_AUDIO_BASE_URL"])


def advance(
    story: KathaStory, db: Any, *, http: v.Http | None = None, storage: v.Storage | None = None
) -> tuple[list[KathaAudio], Status]:
    """(audio, status) for a story the read path found no audio for. Never raises: TTS,
    Storage or database trouble is "none" now, and the next request tries again."""
    voice = chosen_voices().get(story.lang)
    if not enabled() or not voice or not story.segments:
        return [], "none"
    key = v.audio_key(story)
    try:
        if db.execute("INSERT INTO katha_audio_job (audio_key) VALUES (%s) ON CONFLICT DO NOTHING "
                      "RETURNING 1", (key,)).fetchone():  # fmt: skip
            return [], "pending"  # filed; the next request reads the first chapter
        if not db.execute(
            "UPDATE katha_audio_job SET claimed_until = now() + make_interval(secs => %s) "
            "WHERE audio_key = %s AND (claimed_until IS NULL OR claimed_until < now()) RETURNING 1",
            (CLAIM_S, key),
        ).fetchone():
            return [], "pending"  # another request is reading a chapter right now
        try:
            http = http or v.adc_http()
            audio, sent = v.read_aloud(story, voice, http, storage or _storage(http), DailyBudget(db, daily_cap()),
                                       max_new=1)  # fmt: skip
        finally:
            db.execute("UPDATE katha_audio_job SET claimed_until = NULL WHERE audio_key = %s", (key,))
    except v.BudgetSpent as e:
        log.warning("katha audio on demand: %s", e)
        return [], "none"
    except Exception:
        log.warning("katha audio on demand failed for %s %s", story.subject, story.lang, exc_info=True)
        return [], "none"
    if not audio:
        return [], "pending"
    v.forget(story)  # the read path's remembered miss is stale now
    return audio, "ready"
