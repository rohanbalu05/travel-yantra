"""The Katha pipeline (design/katha-style.md): facts → outline → draft → self-critique
and one revision → checks. A draft that fails the checks is regenerated once; a
second failure is an error, never a shipped story.

Model calls go through core.llm. Each is logged on logger guide.katha with its
step, so the live calls behind a taste-gate pack can be counted.

The 10-minute story is written and revised chapter by chapter: each call stays
short enough for one timeout, and each chapter gets its own hook.
"""

from __future__ import annotations

import logging
import re
import typing
from typing import Any, Literal

from pydantic import BaseModel, Field

from ty_contracts import KathaStory, StorySegment

from . import checks
from .facts import Fact, Subject, fitting_length

log = logging.getLogger("guide.katha")

ATTEMPTS = 2
TIMEOUT_S = 60  # per call; long-form output does not fit core.llm's 20 s default
#: Thinking tokens count toward the cap: at "low", a long prompt used ~2,900 of 3,000 and
#: the story was cut at ~100 words. Drafts and rewrites think minimally, with room to spare.
MAX_TOKENS = 6000
#: The model undershoots long single drafts (~500 of 750 words) and lands chapter-sized ones.
CHAPTERS = {2: 1, 5: 2, 10: 4}
#: Labels the contract accepts. Anything else folds into "history" (the text keeps
#: both versions of a disputed claim either way).
CONTRACT_LABELS = set(typing.get_args(StorySegment.model_fields["label"].annotation))
LABEL_LINE = re.compile(r"^\s*\[(HISTORY|LEGEND|DISPUTED)\]\s*$", re.M)
SEPARATOR = re.compile(r"^\s*={3,}\s*$", re.M)
#: A rewrite much shorter than its draft was cut off, not edited; keep the draft.
MIN_REWRITE_RATIO = 0.85


class KathaFailed(RuntimeError):
    """The story could not pass its checks; problems lists why."""

    def __init__(self, problems: list[str], drafts: list[str] = ()):
        super().__init__("; ".join(problems[:5]))
        self.problems = problems
        self.drafts = list(drafts)  # the last attempt's text, for diagnosis


class Beat(BaseModel):
    text: str
    facts: list[int] = Field(description="numbers of the facts this beat uses")
    label: Literal["history", "legend", "disputed"]


class Chapter(BaseModel):
    title: str
    hook: str
    gap: str = Field(description="the question this chapter opens and later closes")
    beats: list[Beat]


class Outline(BaseModel):
    theme: str = Field(description="the one line the reader should remember")
    hook: str
    gap: str = Field(description="the question opened early and closed near the end")
    people: list[str]
    bridge: str = Field(description="one link to the reader's own life")
    peak: str = Field(description="the emotional high point, about two-thirds through")
    ending: str = Field(description="the closing image or line; never a summary")
    chapters: list[Chapter]


RULES = """House style (binding):
- One theme; every paragraph serves it.
- Hook in the first two sentences: a person at a moment, a contradiction, or a question.
  Never open with a date, "Located in", "Welcome to" or superlatives.
- Open one curiosity gap early and close it near the end.
- People, not lists: someone wants something and meets an obstacle. Facts ride on the story.
- At least one checkable specific per paragraph (a name, a number, an object) from the facts,
  and at least one thing to see, hear, smell or touch.
- Where the facts allow, point the reader's eyes at what is in front of them.
- One bridge to the reader's own life.
- The peak about two-thirds through. End on an image or a line, never a summary, never an
  instruction to visit.
- Honest labels: history must cite its fact; a legend is told as one ("people here say...");
  a disputed claim gives both versions briefly. Never invent a fact, name, date or quote.
- Written for the ear: short sentences mixed with long ones, plain words.
- Never use: nestled, tapestry, testament to, steeped in history, hidden gem, bustling, vibrant,
  breathtaking, awe-inspiring, delve, step back in time, boasts, must-visit, must-see,
  "whether you're a ... or a ...", in conclusion, a blend of, timeless charm, rich heritage;
  no stacked triples of adjectives; never two rhetorical questions in a row."""

FORMAT = """Output format, exactly:
Before every paragraph, a line with its label alone: [HISTORY], [LEGEND] or [DISPUTED].
Cite facts by number in square brackets right after the claim, like [3]. Use only the
numbered facts; cite at least one in every HISTORY and DISPUTED paragraph.
Every LEGEND paragraph says in its own words that it is a legend: "People here say...",
"The story goes...", "Legend has it...". Never tell a legend as plain fact.
No title, no headings, no lists, no notes to the editor, nothing before the first label."""


def facts_block(facts: list[Fact]) -> str:
    return "\n\n".join(
        f"[{f.n}]{' (legend)' if f.is_legend else ''} {f.title or ''}\n{f.body}" for f in facts
    )


def outline_prompt(subject: Subject, length: int, facts: list[Fact]) -> str:
    chapters = CHAPTERS[length]
    shape = (f"{chapters} chapters, each with its own hook and gap" if chapters > 1
             else "one chapter with three to six beats")  # fmt: skip
    return (
        f"You are planning a {length}-minute spoken story (Katha) about {subject.name}"
        f"{f', {subject.city}' if subject.city and subject.city != subject.name else ''}"
        f" for a traveller standing there.\n\n{RULES}\n\n"
        f"Plan it as {shape}. Use only these facts; give each beat the numbers of the facts "
        f"it uses and label it history, legend or disputed.\n\nFacts:\n\n{facts_block(facts)}"
    )


def draft_prompt(subject: Subject, length: int, outline: Outline, chapter: int, facts: list[Fact]) -> str:
    n = len(outline.chapters)
    low, high = checks.BANDS[length]
    lo, hi = low * 11 // 10 // n, high * 9 // 10 // n  # aim inside the band, not at its edge
    place = "the whole story" if n == 1 else f"chapter {chapter + 1} of {n}"
    if n > 1 and chapter == n - 1:
        place += " (the last: close the story's gap and land the ending)"
    return (
        f"Write {place} of a {length}-minute spoken story about {subject.name}: between "
        f"{lo} and {hi} words (do not count; write fully and stop at the ending).\n\n{RULES}\n\n{FORMAT}\n\nOutline:\n{outline.model_dump_json(indent=1)}\n\n"
        f"Write only: {outline.chapters[chapter].model_dump_json()}\n\nFacts:\n\n{facts_block(facts)}"
    )


def critique_prompt(subject: Subject, outline: Outline, draft: str, words: int, facts: list[Fact]) -> str:
    return (
        f"Here is a draft of part of a spoken story about {subject.name}. Its theme: "
        f"{outline.theme!r}.\n\nScore it 1-5 on: hook (would a tired traveller read the third "
        "sentence?), theme, specifics, peak, ending, honesty (labels and citations). Name the three "
        "biggest problems. Then rewrite it once to fix them, keeping the facts, the citations and "
        f"the length: about as long as the draft, never shorter, never more than {words * 3 // 2} words.\n\n{RULES}\n\nReply as: the scores and problems, then a line with "
        f"=== alone, then the rewrite.\n\n{FORMAT}\n\nDraft:\n\n{draft}\n\nFacts:\n\n{facts_block(facts)}"
    )


def parse(text: str) -> list[tuple[str, str]]:
    """[(label, paragraph)] from the labelled format; text before the first label is dropped."""
    parts = LABEL_LINE.split(text)
    out = []
    for label, body in zip(parts[1::2], parts[2::2], strict=True):
        for para in re.split(r"\n\s*\n", body.strip()):
            # Lists, headings and separators are notes the model left, not story.
            if para.strip() and not re.match(r"\s*([-*#•]|={3,}|\d+\.\s)", para):
                out.append((label.lower(), " ".join(para.split())))
    return out


def renumber(segments: list[tuple[str, str]], facts: list[Fact]) -> tuple[list[StorySegment], list[str]]:
    """Markers in order of first use, sources to match (identical sources share a number)."""
    sources: list[str] = []

    def sub(m: re.Match) -> str:
        source = facts[int(m.group(1)) - 1].source
        if source not in sources:
            sources.append(source)
        return f"[{sources.index(source) + 1}]"

    out = []
    for label, text in segments:
        text = re.sub(r"(\[\d+\])(?:\s*\1)+", r"\1", checks.MARKER.sub(sub, text))
        text = re.sub(r"(\[\d+\])\[\1\]", r"\1", text)
        label = label if label in CONTRACT_LABELS else "history"
        out.append(StorySegment(label=label, text=text))
    return out, sources


async def _chapter(model: Any, subject, length, outline, i, facts, words) -> tuple[str, str]:
    log.info("katha model call: draft %s ch%d/%d", subject.name, i + 1, len(outline.chapters))
    draft = await model.text(draft_prompt(subject, length, outline, i, facts), tier="flash",
                             thinking="minimal", max_output_tokens=MAX_TOKENS, temperature=0.7,
                             timeout_s=TIMEOUT_S)  # fmt: skip
    log.info("katha model call: critique %s ch%d/%d", subject.name, i + 1, len(outline.chapters))
    reply = await model.text(critique_prompt(subject, outline, draft, words, facts), tier="flash",
                             thinking="minimal", max_output_tokens=MAX_TOKENS, temperature=0.4,
                             timeout_s=TIMEOUT_S)  # fmt: skip
    parts = SEPARATOR.split(reply)
    critique, revised = (parts[0], parts[-1]) if len(parts) > 1 else (reply, "")
    # No separator, no labels, or a rewrite that was cut short: keep the draft.
    if parse(revised) and _words(revised) >= MIN_REWRITE_RATIO * _words(draft):
        return revised, critique.strip()
    return draft, critique.strip() + "\n(rewrite not used: missing or shorter than the draft)"


def _words(text: str) -> int:
    return checks.words(" ".join(p for _, p in parse(text)))


async def write(model: Any, subject: Subject, length_min: int, facts: list[Fact], lang: str = "en"):
    """(KathaStory, notes). notes keeps the outline and the critiques for the taste gate."""
    length = fitting_length(length_min, len(facts))
    if not length:
        raise KathaFailed([f"only {len(facts)} sourced facts; too thin for a story"])
    problems: list[str] = []
    for attempt in range(1, ATTEMPTS + 1):
        log.info("katha model call: outline %s %dmin (attempt %d)", subject.name, length, attempt)
        outline = await model.json(outline_prompt(subject, length, facts), Outline,
                                   tier="flash", thinking="low", timeout_s=TIMEOUT_S)  # fmt: skip
        low, high = checks.BANDS[length]
        words = low * 11 // 10 // max(len(outline.chapters), 1)
        texts, critiques = [], []
        for i in range(len(outline.chapters)):
            text, critique = await _chapter(model, subject, length, outline, i, facts, words)
            texts.append(text)
            critiques.append(critique)
        segments = parse("\n\n".join(texts))
        problems = checks.problems(segments, len(facts), length)
        if not problems:
            story_segments, sources = renumber(segments, facts)
            story = KathaStory(
                subject_kind=subject.kind, subject=subject.name, length_min=length,
                text="\n\n".join(s.text for s in story_segments),
                segments=story_segments, sources=sources, lang=lang,
            )  # fmt: skip
            return story, {"outline": outline.model_dump(), "critiques": critiques, "attempts": attempt}
        log.warning("katha attempt %d failed checks: %s", attempt, problems)
    raise KathaFailed(problems, texts)


def plain_prompt(subject: Subject, length_min: int) -> str:
    """The taste gate's control: what anyone would type into a chatbot."""
    return f"Write a {length_min}-minute story about {subject.name}."
