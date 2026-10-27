import hashlib
import hmac
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import sender as sender_mod
from app.brain import NOT_TEXT, VOICE, Brain
from app.main import SORRY, create_app
from app.sender import CloudApiSender, FakeSender
from app.translate import Translator

PAYLOADS = Path(__file__).parent / "payloads"
SECRET = "test-app-secret"  # fake, used only by these tests
USER = "15550001111"  # fictional sample number


def load(name: str) -> bytes:
    return (PAYLOADS / name).read_bytes()


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "test-verify-token")
    fake = FakeSender()
    app = create_app(brain=Brain(base="", translator=Translator(base="")), sender=fake)
    with TestClient(app) as client:
        yield client, fake


def post(client, body: bytes, signature: str | None = None):
    headers = {"content-type": "application/json"}
    headers["x-hub-signature-256"] = signature if signature is not None else sign(body)
    return client.post("/webhook", content=body, headers=headers)


def test_verify_returns_challenge(bot):
    client, _ = bot
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "test-verify-token",
        "hub.challenge": "42",
    }
    r = client.get("/webhook", params=params)
    assert r.status_code == 200 and r.text == "42"


@pytest.mark.parametrize(
    "params",
    [
        {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"},
        {"hub.mode": "unsubscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "42"},
        {},
    ],
)
def test_verify_rejects(bot, params):
    client, _ = bot
    assert client.get("/webhook", params=params).status_code == 403


def test_verify_rejects_when_token_unset(bot, monkeypatch):
    client, _ = bot
    monkeypatch.delenv("WHATSAPP_VERIFY_TOKEN")
    params = {"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "42"}
    assert client.get("/webhook", params=params).status_code == 403


@pytest.mark.parametrize(
    "signature", ["", "sha256=" + "0" * 64, sign(b"other body"), sign(b"x", secret="other")]
)
def test_bad_signature_is_rejected_and_nothing_sent(bot, signature):
    client, fake = bot
    body = load("text_en.json")
    assert post(client, body, signature).status_code == 401
    assert fake.sent == []


def test_signature_needs_the_secret(bot, monkeypatch):
    client, fake = bot
    monkeypatch.delenv("WHATSAPP_APP_SECRET")
    body = load("text_en.json")
    assert post(client, body, sign(body, secret="")).status_code == 401
    assert fake.sent == []


def test_english_trip_gets_a_plan(bot):
    client, fake = bot
    assert post(client, load("text_en.json")).status_code == 200
    [(to, reply)] = fake.sent
    assert to == USER
    assert "Goa from Bengaluru" in reply and "Day 1" in reply and "Budget: ₹" in reply


def test_hinglish_trip_gets_a_plan(bot):
    client, fake = bot
    post(client, load("text_hinglish.json"))
    [(_, reply)] = fake.sent
    assert "Day 1" in reply


def test_hindi_question_goes_to_the_guide(bot):
    client, fake = bot
    post(client, load("text_hindi.json"))
    [(_, reply)] = fake.sent
    assert "शाकाहारी" in reply


def test_voice_note_gets_text_only_reply(bot):
    client, fake = bot
    post(client, load("voice.json"))
    assert fake.sent == [(USER, VOICE)]


def test_other_media_gets_text_only_reply(bot):
    client, fake = bot
    payload = json.loads(load("voice.json"))
    msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    msg.update(type="image", id="wamid.SAMPLE.image")
    post(client, json.dumps(payload).encode())
    assert fake.sent == [(USER, NOT_TEXT)]


def test_location_is_acknowledged(bot):
    client, fake = bot
    post(client, load("location.json"))
    [(_, reply)] = fake.sent
    assert reply.startswith("Got your location")


def test_status_updates_send_nothing(bot):
    client, fake = bot
    assert post(client, load("status.json")).status_code == 200
    assert fake.sent == []


def test_retried_webhook_replies_once(bot):
    client, fake = bot
    body = load("voice.json")
    post(client, body)
    post(client, body)
    assert len(fake.sent) == 1


def test_brain_failure_sends_sorry(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)

    class Broken(Brain):
        async def handle(self, msg, notify=None, audio=None):
            raise RuntimeError("api down")

    fake = FakeSender()
    with TestClient(create_app(brain=Broken(base=""), sender=fake)) as client:
        assert post(client, load("text_en.json")).status_code == 200
    assert fake.sent == [(USER, SORRY)]


def test_non_json_body_is_400(bot):
    client, _ = bot
    assert post(client, b"not json").status_code == 400


def _fake_graph(monkeypatch):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"messages": [{"id": "wamid.SAMPLE.out"}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        sender_mod.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    return seen


async def test_cloud_sender_posts_to_graph(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "fake-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "100000000000001")
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", f"+{USER}, 15550002222")
    seen = _fake_graph(monkeypatch)
    await CloudApiSender().send_text(USER, "hello")
    [req] = seen
    assert req.url.path.endswith("/100000000000001/messages")
    assert req.headers["authorization"] == "Bearer fake-token"
    assert json.loads(req.content)["to"] == USER
    assert json.loads(req.content)["text"]["body"] == "hello"


@pytest.mark.parametrize("allowed", ["", "15550002222"])
async def test_cloud_sender_only_messages_allowed_recipients(monkeypatch, allowed):
    monkeypatch.setenv("WHATSAPP_TOKEN", "fake-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "100000000000001")
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", allowed)
    seen = _fake_graph(monkeypatch)
    await CloudApiSender().send_text(USER, "hello")
    assert seen == []


@pytest.mark.parametrize(
    "allowed",
    [
        f"+{USER}",
        f" {USER[:1]} {USER[1:5]}-{USER[5:]} ",
        f"0{USER}",
        f"x;{USER}",
        "+1 (555) 000-1111",
    ],
)
async def test_allowed_recipients_ignore_formatting(monkeypatch, allowed):
    monkeypatch.setenv("WHATSAPP_TOKEN", "fake-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "100000000000001")
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", allowed)
    seen = _fake_graph(monkeypatch)
    await CloudApiSender().send_text(USER, "hello")
    assert len(seen) == 1


def test_ten_digit_entry_means_india():
    allowed = {"9800000000"}  # fictional
    assert sender_mod.is_allowed("919800000000", allowed)
    assert not sender_mod.is_allowed("19800000000", allowed)
    assert not sender_mod.is_allowed("", allowed)


async def test_graph_error_logs_code_not_message(monkeypatch, caplog):
    monkeypatch.setenv("WHATSAPP_TOKEN", "fake-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "100000000000001")
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", USER)
    err = {"error": {"message": f"bad recipient {USER}", "type": "OAuthException", "code": 190}}
    real = httpx.AsyncClient
    monkeypatch.setattr(
        sender_mod.httpx,
        "AsyncClient",
        lambda **kw: real(
            transport=httpx.MockTransport(lambda r: httpx.Response(401, json=err)), **kw
        ),
    )
    await CloudApiSender().send_text(USER, "hello")
    assert "send failed: HTTP 401 code=190" in caplog.text and "OAuthException" in caplog.text
    assert USER not in caplog.text


def test_failed_delivery_status_is_logged(bot, caplog):
    client, fake = bot
    payload = json.loads(load("status.json"))
    status = payload["entry"][0]["changes"][0]["value"]["statuses"][0]
    status.update(
        status="failed", errors=[{"code": 131030, "title": "Recipient not in allowed list"}]
    )
    assert post(client, json.dumps(payload).encode()).status_code == 200
    assert "131030 Recipient not in allowed list" in caplog.text
    assert USER not in caplog.text and fake.sent == []


def test_planning_note_is_sent_before_the_plan(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)

    class Slow(Brain):
        async def _handle(self, msg):
            from app.brain import NOTIFY

            await NOTIFY.get()("working…")
            return "the plan"

    fake = FakeSender()
    with TestClient(create_app(brain=Slow(base=""), sender=fake)) as client:
        post(client, load("text_en.json"))
    assert fake.sent == [(USER, "working…"), (USER, "the plan")]


def test_verify_token_is_never_logged(bot, caplog):
    client, _ = bot
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "test-verify-token",
        "hub.challenge": "42",
    }
    client.get("/webhook", params=params)
    client.get("/webhook", params={**params, "hub.verify_token": "guess-token"})
    assert "test-verify-token" not in caplog.text and "guess-token" not in caplog.text


def test_story_audio_follows_its_text(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)

    class Teller(Brain):
        async def _handle(self, msg):
            from app.brain import AUDIO

            AUDIO.get().extend(["https://audio.example/1.mp3", "https://audio.example/2.mp3"])
            return "the story"

    fake = FakeSender()
    with TestClient(create_app(brain=Teller(base=""), sender=fake)) as client:
        post(client, load("text_en.json"))
    assert fake.sent == [(USER, "the story")]
    assert fake.audio == [
        (USER, "https://audio.example/1.mp3"),
        (USER, "https://audio.example/2.mp3"),
    ]


async def test_cloud_sender_sends_audio_by_link(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "fake-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "100000000000001")
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", USER)
    seen = _fake_graph(monkeypatch)
    await CloudApiSender().send_audio(USER, "https://audio.example/1.mp3")
    body = json.loads(seen[0].content)
    assert body["type"] == "audio" and body["audio"] == {"link": "https://audio.example/1.mp3"}
