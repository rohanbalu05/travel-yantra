import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import review_web_strings as r


def test_clean_string_has_no_flags():
    assert r.flags("Plan my trip", "hi", "मेरी यात्रा की योजना बनाएं") == []


def test_brand_names_and_native_digits_are_fine():
    assert r.flags("Open IRCTC", "ta", "IRCTC-யைத் திறங்கள்") == []
    assert r.flags("Takes about 15 seconds.", "bn", "প্রায় ১৫ সেকেন্ড লাগে।") == []


def test_lost_placeholder_and_number():
    assert "placeholder" in r.flags("Planning your {dest} trip", "hi", "आपकी यात्रा")
    assert "number" in r.flags("Under 18", "hi", "18 से कम 5")


def test_term_and_katha_flags():
    assert r.flags("Plan a trip", "te", "యాత్ర ప్లాన్ చేయండి") == ["term:trip"]
    assert r.flags("Katha", "bn", "কথা") == ["term:katha"]


def test_untranslated_and_missing():
    assert r.flags("Search", "kn", "Search") == ["wrong_script", "untranslated"]
    assert r.flags("Search", "kn", None) == ["missing"]


def test_extra_table_parses_both_key_forms():
    tsx = 'const EXTRA = {\n  Home: { hi: "होम", kn: "ಮುಖಪುಟ" },\n  "My trips": { hi: "मेरी यात्राएं" },\n};'
    assert r.extra_table(tsx) == {
        "Home": {"hi": "होम", "kn": "ಮುಖಪುಟ"},
        "My trips": {"hi": "मेरी यात्राएं"},
    }


def test_web_strings_load():
    total, _ = r.review()
    assert total > 100
    assert r.load()["Home"][0] == "index.tsx EXTRA"  # the EXTRA table still parses
