import json
import logging
from types import SimpleNamespace

import pytest

from app import main
from app.service import TranslationService
from app.translator import FakeTranslator, GeminiTranslator, normalise


class FakeClient:
    """Stands in for google.genai.Client: answers with canned JSON, records prompts."""

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.prompts.append((model, contents, config))
        text = self.reply(contents) if callable(self.reply) else self.reply
        usage = SimpleNamespace(prompt_token_count=40, candidates_token_count=45)
        return SimpleNamespace(text=text, usage_metadata=usage)


def batch(prompt: str) -> list[str]:
    """The JSON array of texts at the end of the prompt."""
    return json.loads(prompt.rsplit("\n\n", 1)[-1])


def echo_hindi(prompt: str) -> str:
    texts = batch(prompt)
    return json.dumps([f"हिंदी {t} |" for t in texts], ensure_ascii=False)


@pytest.mark.parametrize(
    "text, lang, out",
    [
        ("गोवा अच्छा है |", "hi", "गोवा अच्छा है।"),
        ("কলকাতা সুন্দর。", "bn", "কলকাতা সুন্দর।"),
        ("மதுரை அழகு。", "ta", "மதுரை அழகு."),
        ("गोवा अच्छा है।", "hi", "गोवा अच्छा है।"),
        ("A | B", "hi", "A | B"),
    ],
)
def test_normalise(text, lang, out):
    assert normalise(text, lang) == out


def test_one_call_per_batch_normalised_and_logged(caplog):
    client = FakeClient(echo_hindi)
    tr = GeminiTranslator(client=client, model="test-model")
    with caplog.at_level(logging.INFO, logger="ty.translate.gemini"):
        out = tr.translate(["Goa is lovely.", "XQ0Z at sunrise [1]."], "hi")
    assert out == ["हिंदी Goa is lovely.।", "हिंदी XQ0Z at sunrise [1].।"]
    [(model, prompt, config)] = client.prompts
    assert model == "test-model" and "Hindi" in prompt and "XQ0Z" in prompt
    assert config["response_mime_type"] == "application/json"
    [rec] = caplog.records
    assert "texts=2" in rec.message and "tokens_in=40" in rec.message
    assert "Goa" not in rec.message  # the log carries no text


@pytest.mark.parametrize("reply", ['["only one"]', '{"a": 1}', "[1, 2]", "not json"])
def test_bad_reply_raises(reply):
    tr = GeminiTranslator(client=FakeClient(reply))
    with pytest.raises(ValueError):
        tr.translate(["a", "b"], "ta")


def test_empty_batch_makes_no_call():
    client = FakeClient("[]")
    assert GeminiTranslator(client=client).translate([], "kn") == []
    assert client.prompts == []


def test_service_protects_entities_through_gemini():
    def keep_tokens(prompt):
        texts = batch(prompt)
        return json.dumps([f"{t} हिंदी में।" for t in texts], ensure_ascii=False)

    svc = TranslationService(GeminiTranslator(client=FakeClient(keep_tokens)), cache_size=0)
    [r] = svc.translate_checked(["Visit Fontainhas [1]."], "hi", entities=["Fontainhas", "[1]"])
    assert "Fontainhas" in r.text and "[1]" in r.text
    assert "XQ" not in r.text


@pytest.mark.parametrize(
    "env, kind",
    [
        ({}, FakeTranslator),
        ({"TY_TRANSLATOR": "fake"}, FakeTranslator),
        ({"TY_FAKE_TRANSLATOR": "1"}, FakeTranslator),
        ({"TY_TRANSLATOR": "gemini"}, GeminiTranslator),
    ],
)
def test_build_translator(monkeypatch, env, kind):
    for name in ("TY_TRANSLATOR", "TY_FAKE_TRANSLATOR"):
        monkeypatch.delenv(name, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(main, "GeminiTranslator", lambda: GeminiTranslator(client=FakeClient("[]")))
    assert isinstance(main.build_translator(), kind)
