"""Loads the real IndicTrans2 model. Runs in CI only: pytest -m slow."""

import pytest

SAMPLE = (
    "Hampi was the capital of the Vijayanagara Empire. Visit at sunrise to see the "
    "Virupaksha Temple and the stone chariot without the crowds."
)


@pytest.mark.slow
def test_real_model_translates_all_five_languages():
    pytest.importorskip("IndicTransToolkit")
    from app.translator import IndicTrans2Translator, LANGS

    tr = IndicTrans2Translator()
    for lang in LANGS:
        out = tr.translate([SAMPLE], lang)[0]
        assert out and out != SAMPLE
