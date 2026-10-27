"""A deterministic stand-in for the model, for tests and TY_FAKE_LLM=1.

It reads the numbered facts out of the prompt and writes plain labelled
paragraphs from their first sentences, padded to the word target. It is not a
writer; it exists so the pipeline's parsing, renumbering and checks run.
"""

from __future__ import annotations

import re

from . import checks
from .pipeline import Beat, Chapter, Outline

_FACT = re.compile(r"^\[(\d+)\]( \(legend\))? (.*)\n(.+)$", re.M)


def _facts(prompt: str) -> list[tuple[int, bool, str]]:
    block = prompt.rsplit("Facts:\n\n", 1)[-1]
    out = []
    for m in _FACT.finditer(block):
        first = re.split(r"(?<=[.!?])\s", m.group(4).strip(), maxsplit=1)[0].rstrip(".")
        if not checks.slop(first) and not first.endswith("?"):
            out.append((int(m.group(1)), bool(m.group(2)), first))
    return out


class FakeKathaModel:
    async def json(self, prompt: str, schema, tier: str = "flash", **_: object):
        assert schema is Outline
        facts = _facts(prompt)
        m = re.search(r"as (\d+) chapters", prompt)
        chapters = int(m.group(1)) if m else 1
        beats = [Beat(text=t, facts=[n], label="legend" if leg else "history") for n, leg, t in facts]
        return Outline(
            theme="(sample) theme", hook="(sample) hook", gap="(sample) gap", people=[],
            bridge="(sample) bridge", peak="(sample) peak", ending="(sample) ending",
            chapters=[Chapter(title=f"Part {i + 1}", hook="h", gap="g", beats=beats[i::chapters])
                      for i in range(chapters)],
        )  # fmt: skip

    async def text(self, prompt: str, tier: str = "flash", **_: object) -> str:
        if prompt.startswith("Here is a draft"):
            draft = prompt.split("Draft:\n\n", 1)[1].rsplit("\n\nFacts:\n\n", 1)[0]
            return "hook 4, theme 4, specifics 4, peak 3, ending 3, honesty 5\n===\n" + draft
        if "\n" not in prompt:  # the taste gate's plain prompt
            return f"(sample) A plain story. {prompt}"
        target = int(re.search(r"between (\d+) and \d+ words", prompt).group(1))
        facts = _facts(prompt)
        paras, words, i = [], 0, 0
        while words < target and facts:
            n, legend, first = facts[i % len(facts)]
            body = f"People here say {first[0].lower()}{first[1:]} [{n}]." if legend else f"{first} [{n}]."
            paras.append(f"[{'LEGEND' if legend else 'HISTORY'}]\n{body}")
            words += checks.words(body)
            i += 1
        return "\n\n".join(paras)
