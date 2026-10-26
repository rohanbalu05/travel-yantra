"""Loads the real IndicTrans2 model. Runs in CI only: pytest -m slow."""

import os

import pytest

SAMPLE = (
    "Hampi was the capital of the Vijayanagara Empire. Visit at sunrise to see the "
    "Virupaksha Temple and the stone chariot without the crowds."
)


@pytest.mark.slow
def test_real_model_translates_all_five_languages():
    pytest.importorskip("IndicTransToolkit")
    model_dir = os.environ.get("TY_MODEL_DIR")
    if not model_dir:
        pytest.skip("TY_MODEL_DIR (pre-provisioned weights directory) not set")
    from app.translator import LANGS, IndicTrans2Translator

    # Offline: weights are provisioned by the CI job; the test never touches the network.
    tr = IndicTrans2Translator(model_name=model_dir, local_files_only=True)
    for lang in LANGS:
        out = tr.translate([SAMPLE], lang)[0]
        assert out and out != SAMPLE
