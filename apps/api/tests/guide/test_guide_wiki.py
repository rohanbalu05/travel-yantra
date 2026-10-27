import json
from pathlib import Path

import pytest

from guide.wiki import USER_AGENT, WikiClient, paragraphs

FIX = Path(__file__).parent / "fixtures"


class Replay:
    """Recorded Wikimedia responses, keyed by URL; an unknown URL fails the test."""

    def __init__(self, *names: str) -> None:
        self.by_url = {}
        for name in names:
            rec = json.loads((FIX / name).read_text(encoding="utf-8"))
            self.by_url[rec["url"]] = rec["payload"]
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, method, url, headers, body, timeout):
        assert method == "GET" and body is None and timeout > 0
        self.calls.append((url, headers))
        if url not in self.by_url:
            pytest.fail(f"no recording for {url}")
        return self.by_url[url]


def test_mysore_palace_has_native_names_in_all_five_indic_languages() -> None:
    t = Replay("wiki_labels_mysore_palace.json")
    labels = WikiClient(transport=t).labels("Mysore Palace")
    assert labels["qid"] == "Q456575"
    assert labels["labels"]["kn"] == "ಮೈಸೂರು ಅರಮನೆ"
    assert set(labels["labels"]) >= {"hi", "kn", "ta", "te", "bn"}
    assert labels["lat"] == pytest.approx(12.3039, abs=1e-3)
    assert t.calls[0][1]["User-Agent"] == USER_AGENT


def test_summary_and_a_cache_hit_on_repeat() -> None:
    t = Replay("wiki_summary_mysore_palace.json")
    c = WikiClient(transport=t)
    s = c.summary("Mysore Palace")
    assert s["url"] == "https://en.wikipedia.org/wiki/Mysore_Palace" and len(s["extract"].split()) > 50
    assert c.summary("Mysore Palace") == s
    assert len(t.calls) == 1 and c.calls == 1


def test_sections_keep_prose_and_drop_reference_lists() -> None:
    c = WikiClient(transport=Replay("wiki_sections_bom_jesus.json"))
    url, sections = c.sections("Basilica of Bom Jesus")
    assert url == "https://en.wikipedia.org/wiki/Basilica_of_Bom_Jesus"
    headings = [h for h, _ in sections]
    assert headings[0] == "Introduction" and "History" in headings
    assert not {"References", "External links", "See also"} & set(headings)
    assert "Francis Xavier" in " ".join(b for _, b in sections)


def test_paragraphs_drop_scraps_and_cut_walls_on_a_sentence() -> None:
    text = "Short line.\n\n" + " ".join(["Word"] * 30) + ".\n" + ("This is a sentence. " * 60)
    out = paragraphs(text, max_words=50)
    assert len(out) == 2 and out[0].endswith(".")
    assert len(out[1].split()) <= 50 and out[1].endswith(".")
