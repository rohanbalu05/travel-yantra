from fastapi.testclient import TestClient

from app import checks, phrasebook
from app.main import create_app
from app.service import TranslationService
from app.translator import LANGS, FakeTranslator

NAMES = {"Hampi": {"hi": "हम्पी", "kn": "ಹಂಪಿ"}}


class Echo:
    """Translator returning a fixed string per call, to simulate model output."""

    def __init__(self, out):
        self.out, self.calls = out, []

    def translate(self, texts, target, source="en"):
        self.calls.append(list(texts))
        return [self.out(t) for t in texts]


def test_phrasebook_complete_and_in_script():
    book = phrasebook.load()
    assert len(book) >= 95
    for en, row in book.items():
        assert set(row) == set(LANGS), en
        for lang, text in row.items():
            assert text and checks.script_ok(text, lang), (en, lang)


def test_phrasebook_hit_skips_model():
    fake = FakeTranslator()
    svc = TranslationService(fake)
    [r] = svc.translate_checked(["Book now"], "hi")
    assert (r.text, r.via, r.flags) == ("अभी बुक करें", "phrasebook", [])
    assert fake.calls == []


def test_entity_survives_and_uses_native_name():
    model = Echo(lambda t: "यात्रा " + t.replace("Visit ", ""))
    svc = TranslationService(model, entity_names=NAMES, book={})
    [r] = svc.translate_checked(["Visit Hampi"], "hi", entities=["Hampi"])
    assert "Hampi" not in model.calls[0][0]  # model never sees the name
    assert r.text.endswith("हम्पी") and r.flags == []


def test_entity_without_native_name_keeps_original():
    model = Echo(lambda t: "यात्रा " + t.replace("Visit ", ""))
    svc = TranslationService(model, entity_names={}, book={})
    [r] = svc.translate_checked(["Visit Orchha"], "hi", entities=["Orchha"])
    assert "Orchha" in r.text and r.flags == []


def test_dropped_entity_is_flagged():
    svc = TranslationService(Echo(lambda t: "यात्रा"), entity_names=NAMES, book={})
    [r] = svc.translate_checked(["Visit Hampi"], "hi", entities=["Hampi"])
    assert r.flags == ["entity_lost:Hampi"]


def test_wrong_script_flagged():
    svc = TranslationService(Echo(lambda t: "visit the old ruins"), book={})
    [r] = svc.translate_checked(["Visit the ruins today"], "kn")
    assert "wrong_script" in r.flags


def test_length_flagged():
    svc = TranslationService(Echo(lambda t: "ಹ" * 400), book={})
    [r] = svc.translate_checked(["Visit"], "kn")
    assert "length" in r.flags


def test_phrasebook_hits_are_checked():
    svc = TranslationService(FakeTranslator(), book={"Tomorrow": {"hi": "कल"}})
    [r] = svc.translate_checked(["Tomorrow"], "hi")
    assert r.via == "phrasebook" and r.flags == ["length"]


def test_length_counts_restored_entity():
    svc = TranslationService(Echo(lambda t: t), entity_names=NAMES, book={})
    [r] = svc.translate_checked(["Hampi"], "hi", entities=["Hampi"])
    assert r.text == "हम्पी" and r.flags == []


def test_entity_matches_whole_words_only():
    text, slots = checks.protect("Try Goan food in Goa", ["Goa"])
    assert text.startswith("Try Goan food in ") and list(slots.values()) == ["Goa"]


def test_api_returns_via_and_flags():
    with TestClient(create_app()) as c:
        body = c.post("/translate", json={"texts": ["Hello", "Zebra"], "target": "ta"}).json()
        assert body["via"] == ["phrasebook", "model"]
        assert body["translations"][0] == "வணக்கம்"
        assert body["flags"][0] == [] and "wrong_script" in body["flags"][1]  # fake is Latin
