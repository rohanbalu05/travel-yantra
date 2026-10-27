"""Katha read aloud (V3-AF): Google Cloud Text-to-Speech, Chirp 3: HD where it exists.

One MP3 per chapter, each ending on a long pause so chapters breathe when a player
runs them back to back. Citation markers are never read out. Audio is stored under
a key made from the story's own text and language, so a story is read once
and a rewritten story (new PIPELINE_VERSION, new text) gets new audio:

    katha/<audio key>/<lang>/ch<n>.mp3     the chapters
    katha/<audio key>/<lang>/audio.json    the manifest the API attaches to a story

Every character sent to TTS is counted against a Budget before the call. REST and
Application Default Credentials only: no TTS or Storage client library. Tests use fakes.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Callable
from typing import Any, Protocol

from ty_contracts import KathaAudio, KathaStory

from . import checks
from .pipeline import CHAPTERS

log = logging.getLogger(__name__)

TTS = "https://texttospeech.googleapis.com/v1"
GCS_UPLOAD = "https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
LANG_CODE = {"en": "en-IN", "hi": "hi-IN", "kn": "kn-IN", "ta": "ta-IN", "te": "te-IN", "bn": "bn-IN"}
#: Best first. Chirp 3: HD takes `markup` with pause tags; the older families take SSML.
FAMILIES = ("Chirp3-HD", "Neural2", "Wavenet", "Standard")
#: A warm, unhurried narrator where Chirp 3: HD has it; any voice of the family otherwise.
PREFERRED = ("Charon", "Kore", "Achird", "Aoede")
MAX_BYTES = 4800  # the API takes 5,000 bytes of input per request; Indic scripts are 3 a char
TIMEOUT_S = 60
RETRY_WAITS_S = (5, 15, 30, 60)  # then one last try


class BudgetSpent(RuntimeError):
    pass


class Budget:
    """Characters sent to TTS, stopped before a call would pass the limit."""

    def __init__(self, limit: int):
        self.limit, self.used = limit, 0

    def take(self, n: int) -> None:
        if self.used + n > self.limit:
            raise BudgetSpent(f"TTS budget: {self.used} used, {n} more would pass {self.limit}")
        self.used += n


class Storage(Protocol):
    def get(self, name: str) -> bytes | None: ...
    def put(self, name: str, data: bytes, content_type: str) -> str: ...


#: (method, url, json body or None, raw bytes or None, headers) -> (status, body bytes)
Http = Callable[[str, str, dict | None, bytes | None, dict], tuple[int, bytes]]


def adc_http() -> Http:
    """Authorised HTTP with Application Default Credentials, billed to the trial project."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(creds)
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")

    def call(method, url, body, data, headers):
        h = {"x-goog-user-project": project, **headers} if project else headers
        r = session.request(method, url, json=body, data=data, headers=h, timeout=TIMEOUT_S)
        return r.status_code, r.content

    return call


class GcsStorage:
    """A bucket over the JSON API; objects are read back through their public URL."""

    def __init__(self, bucket: str, http: Http, base_url: str | None = None):
        self.bucket, self.http = bucket, http
        self.base = (base_url or f"https://storage.googleapis.com/{bucket}").rstrip("/")

    def url(self, name: str) -> str:
        return f"{self.base}/{name}"

    def get(self, name):
        status, body = self.http("GET", self.url(name), None, None, {})
        return body if status == 200 else None

    def put(self, name, data, content_type):
        url = GCS_UPLOAD.format(bucket=self.bucket) + f"?uploadType=media&name={name}"
        status, body = self.http("POST", url, None, data, {"Content-Type": content_type})
        if status != 200:
            raise RuntimeError(f"upload {name}: HTTP {status} {body[:200]!r}")
        return self.url(name)


def _transient(status: int, body: bytes) -> bool:
    """Worth a retry: quota, overload, or an API enabled minutes ago that not every Google
    frontend knows yet (403 "has not been used ... or it is disabled"; seen live)."""
    return status in (429, 500, 503) or (status == 403 and b"has not been used" in body)


def _with_retry(http: Http, method, url, body, data, headers) -> tuple[int, bytes]:
    """A failed TTS request is not billed, so retrying never counts characters twice."""
    for wait in RETRY_WAITS_S:
        status, raw = http(method, url, body, data, headers)
        if not _transient(status, raw):
            return status, raw
        log.warning("tts %s HTTP %d; retrying in %d s", url.rsplit("/", 1)[-1][:30], status, wait)
        time.sleep(wait)
    return http(method, url, body, data, headers)


def voices(http: Http, lang: str) -> list[str]:
    """Every voice name TTS lists for the language (en-IN etc.), sorted."""
    status, body = _with_retry(http, "GET", f"{TTS}/voices?languageCode={LANG_CODE[lang]}", None, None, {})
    if status != 200:
        raise RuntimeError(f"voices {lang}: HTTP {status} {body[:200]!r}")
    code = LANG_CODE[lang]
    return sorted(v["name"] for v in json.loads(body).get("voices", []) if code in v["languageCodes"])


def pick_voice(names: list[str]) -> str | None:
    """The best family present (Chirp 3: HD, then Neural2, WaveNet, Standard), and in it the
    preferred narrator if there is one."""
    for family in FAMILIES:
        found = [n for n in names if f"-{family}-" in n]
        if not found:
            continue
        by_speaker = {n.rsplit("-", 1)[1]: n for n in found}
        return next((by_speaker[w] for w in PREFERRED if w in by_speaker), found[0])
    return None


def speakable(text: str) -> str:
    """What a listener hears: no [n] markers, no doubled spaces."""
    text = checks.MARKER.sub("", text)
    text = re.sub(r"\s+([.,;:!?।])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def chapters(story: KathaStory, starts: list[int] | None = None) -> list[list[str]]:
    """The story's paragraphs grouped by chapter. starts: the segment index each chapter
    begins at, when the pipeline kept it; otherwise the segments split evenly."""
    paras = [speakable(s.text) for s in story.segments] or [speakable(story.text)]
    if not starts:
        n = min(CHAPTERS[story.length_min], len(paras))
        size = -(-len(paras) // n)
        starts = list(range(0, len(paras), size))
    bounds = [*starts, len(paras)]
    return [paras[a:b] for a, b in zip(bounds, bounds[1:], strict=False) if paras[a:b]]


def requests_for(paras: list[str], chirp: bool, *, last: bool) -> list[dict]:
    """TTS inputs for one chapter, each under MAX_BYTES, paragraphs never split unless a
    single one is too long (then at sentence ends). Pauses: short between paragraphs,
    long at the chapter's end."""
    pieces: list[str] = []
    for p in paras:
        if len(p.encode()) <= MAX_BYTES - 40:
            pieces.append(p)
        else:
            pieces += [s for s in re.split(r"(?<=[.!?।])\s+", p) if s]
    joiner, end = ("\n[pause]\n", "\n[pause long]") if chirp else ('<break time="700ms"/>', '<break time="1800ms"/>')
    out, cur = [], ""
    for piece in pieces:
        piece = piece if chirp else _xml(piece)
        cand = f"{cur}{joiner}{piece}" if cur else piece
        if len(cand.encode()) + 40 > MAX_BYTES and cur:
            out.append(cur)
            cand = piece
        cur = cand
    if cur:
        out.append(cur + ("" if last else end))
    return [{"markup": t} if chirp else {"ssml": f"<speak>{t}</speak>"} for t in out]


def _xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def characters(inputs: list[dict]) -> int:
    """What TTS bills: the characters sent, markup and SSML included."""
    return sum(len(next(iter(i.values()))) for i in inputs)


def synthesize(http: Http, inputs: list[dict], voice: str, lang: str, budget: Budget) -> bytes:
    """One chapter's MP3: each request's MP3 frames, back to back (MP3 concatenates)."""
    audio = b""
    for item in inputs:
        budget.take(characters([item]))
        body = {"input": item, "voice": {"languageCode": LANG_CODE[lang], "name": voice},
                "audioConfig": {"audioEncoding": "MP3", "speakingRate": 0.95}}  # fmt: skip
        status, raw = _with_retry(http, "POST", f"{TTS}/text:synthesize", body, None, {})
        if status != 200:
            raise RuntimeError(f"synthesize {voice}: HTTP {status} {raw[:200]!r}")
        audio += base64.b64decode(json.loads(raw)["audioContent"])
    return audio


def audio_key(story: KathaStory) -> str:
    """The story's own words and language: the API can find the audio from the story alone,
    and a rewritten story gets new audio. The manifest records which voice read it."""
    raw = json.dumps([story.lang, story.text], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def prefix(story: KathaStory) -> str:
    return f"katha/{audio_key(story)}/{story.lang}"


def read_aloud(
    story: KathaStory,
    voice: str,
    http: Http,
    storage: Storage,
    budget: Budget,
    starts: list[int] | None = None,
) -> tuple[list[KathaAudio], int]:
    """(the chapters' audio, characters sent now). Audio already stored costs nothing."""
    where = prefix(story)
    if (manifest := storage.get(f"{where}/audio.json")) is not None:
        return [KathaAudio(**a) for a in json.loads(manifest)], 0
    chirp, groups, out, sent = "-Chirp3-HD-" in voice, chapters(story, starts), [], 0
    for n, paras in enumerate(groups, start=1):
        inputs = requests_for(paras, chirp, last=n == len(groups))
        mp3 = synthesize(http, inputs, voice, story.lang, budget)
        chars = characters(inputs)
        url = storage.put(f"{where}/ch{n}.mp3", mp3, "audio/mpeg")
        out.append(KathaAudio(chapter=n, url=url, voice=voice, characters=chars))
        sent += chars
        log.warning("katha audio: %s %s ch%d %d chars", story.subject, story.lang, n, chars)
    storage.put(f"{where}/audio.json", json.dumps([a.model_dump() for a in out]).encode(),
                "application/json")  # fmt: skip
    return out, sent


def attach(story: KathaStory, fetch: Callable[[str], Any] | None = None) -> list[KathaAudio]:
    """The stored audio for a story, if any: the API's read path (one small public GET,
    3 s timeout). Needs KATHA_AUDIO_BASE_URL; any failure means no audio, never an error."""
    base = os.environ.get("KATHA_AUDIO_BASE_URL")
    if not base:
        return []
    try:
        raw = (fetch or _fetch)(f"{base.rstrip('/')}/{prefix(story)}/audio.json")
        return [KathaAudio(**a) for a in json.loads(raw)] if raw else []
    except Exception:
        log.warning("katha audio manifest unreadable for %s", story.subject, exc_info=True)
        return []


def _fetch(url: str) -> bytes | None:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):  # not read aloud yet
            return None
        raise
