import hashlib
import hmac
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import chat as chat_mod
from app import sender as sender_mod
from app.chat import NOT_TEXT, Chat, client_id
from app.main import SORRY, create_app, split
from app.sender import CloudApiSender, FakeSender

PAYLOADS = Path(__file__).parent / "payloads"
SECRET = "test-app-secret"  # fake, used only by these tests
USER = "15550001111"  # fictional sample number
API = "http://api.test"


def load(name: str) -> bytes:
    return (PAYLOADS / name).read_bytes()


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def sse(*events: dict) -> str:
    return "".join(f": ping\n\ndata: {json.dumps(e)}\n\n" for e in events)


class FakeApi:
    """POST /chat answers with `events`; the Graph API serves one voice note."""

    def __init__(self) -> None:
        self.events: list[dict] = [{"type": "text", "text": "the reply"}, {"type": "done"}]
        self.chats: list[httpx.Request] = []
        self.media = b"OggS voice"
        self.status = 200

    def bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.chats]

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if req.url.path == "/chat":
            self.chats.append(req)
            return httpx.Response(self.status, text=sse(*self.events))
        if req.url.host == "graph.facebook.com":
            assert req.headers["authorization"] == "Bearer fake-token"
            info = {"url": "https://media.example/v.ogg", "mime_type": "audio/ogg", "file_size": 10}
            return httpx.Response(200, json=info)
        if req.url.host == "media.example":
            return httpx.Response(200, content=self.media)
        return httpx.Response(404)


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()
    real = httpx.AsyncClient
    monkeypatch.setattr(
        chat_mod.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(fake), **kw)
    )
    return fake


@pytest.fixture
def bot(monkeypatch, api):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "test-verify-token")
    fake = FakeSender()
    app = create_app(chat=Chat(base=API, token="fake-token"), sender=fake)
    with TestClient(app) as client:
        yield client, fake


def post(client, body: bytes, signature: str | None = None):
    headers = {"content-type": "application/json"}
    headers["x-hub-signature-256"] = signature if signature is not None else sign(body)
    return client.post("/webhook", content=body, headers=headers)


class Canned:
    """A chat that returns a fixed reply (and notes or audio) without any HTTP."""

    def __init__(self, reply="the plan", notes=(), audio=(), boom=False) -> None:
        self.reply, self.notes, self.audio, self.boom = reply, notes, audio, boom

    async def handle(self, msg, notify=None, audio=None):
        if self.boom:
            raise RuntimeError("api down")
        for n in self.notes:
            await notify(n)
        audio.extend(self.audio)
        return self.reply


def run(monkeypatch, chat) -> FakeSender:
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)
    fake = FakeSender()
    with TestClient(create_app(chat=chat, sender=fake)) as client:
        post(client, load("text_en.json"))
    return fake


def test_text_goes_to_chat_and_the_reply_comes_back(bot, api):
    client, fake = bot
    api.events = [
        {"type": "note", "text": "Working on your plan now"},
        {"type": "plan", "plan_id": "p1"},
        {"type": "text", "text": "Goa from Bengaluru\nDay 1: Basilica"},
        {"type": "chips", "chips": ["share"]},
        {"type": "done", "plan_id": "p1", "plan_changed": True},
    ]
    assert post(client, load("text_en.json")).status_code == 200
    assert fake.sent == [
        (USER, "Working on your plan now"),
        (USER, "Goa from Bengaluru\nDay 1: Basilica"),
    ]
    [body] = api.bodies()
    assert body["channel"] == "whatsapp" and "Goa" in body["text"]
    # The conversation id is keyed by the number, but neither holds nor reveals it.
    cid = api.chats[0].headers["x-client-id"]
    assert cid == client_id(USER) and cid.startswith("wa-") and USER not in cid


def test_same_sender_same_conversation(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)
    assert client_id("+1 555 000 1111") == client_id(USER) != client_id("15550002222")
    other = client_id(USER)
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "another-secret")
    assert client_id(USER) != other


def test_voice_note_is_downloaded_and_sent_as_audio(bot, api):
    client, fake = bot
    api.events = [
        {"type": "heard", "text": "गोवा की यात्रा"},
        {"type": "text", "text": "ठीक है"},
        {"type": "done"},
    ]
    post(client, load("voice.json"))
    [body] = api.bodies()
    assert body["audio"]["data"] == "T2dnUyB2b2ljZQ=="  # base64 of the fake media
    assert body["audio"]["mime"].startswith("audio/ogg")
    assert fake.sent == [(USER, "🎤 “गोवा की यात्रा”"), (USER, "ठीक है")]


def test_voice_note_too_long_is_refused(bot, api, monkeypatch):
    client, fake = bot
    monkeypatch.setattr(chat_mod, "MAX_AUDIO_BYTES", 4)
    post(client, load("voice.json"))
    assert api.chats == [] and fake.sent[0][1].startswith("That voice note is too long")


def test_other_media_gets_text_only_reply(bot, api):
    client, fake = bot
    payload = json.loads(load("voice.json"))
    msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    msg.update(type="image", id="wamid.SAMPLE.image")
    post(client, json.dumps(payload).encode())
    assert fake.sent == [(USER, NOT_TEXT)] and api.chats == []


def test_location_goes_to_chat(bot, api):
    client, _ = bot
    post(client, load("location.json"))
    [body] = api.bodies()
    assert set(body["location"]) == {"lat", "lng"} and "text" not in body


def test_chat_http_error_says_busy(bot, api):
    client, fake = bot
    api.status = 503
    post(client, load("text_en.json"))
    assert fake.sent == [(USER, chat_mod.BUSY)]


def test_senders_not_allowed_cost_nothing(monkeypatch, api):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", "15550002222")
    monkeypatch.setenv("WHATSAPP_TOKEN", "fake-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "100000000000001")
    with TestClient(create_app(chat=Chat(base=API, token="fake-token"))) as client:
        post(client, load("voice.json"))
    assert api.chats == []


def test_chat_failure_sends_sorry(monkeypatch):
    assert run(monkeypatch, Canned(boom=True)).sent == [(USER, SORRY)]


def test_planning_note_is_sent_before_the_plan(monkeypatch):
    fake = run(monkeypatch, Canned(notes=["working…"]))
    assert fake.sent == [(USER, "working…"), (USER, "the plan")]


def test_story_audio_follows_its_text(monkeypatch):
    urls = ["https://audio.example/1.mp3", "https://audio.example/2.mp3"]
    fake = run(monkeypatch, Canned(reply="the story", audio=urls))
    assert fake.sent == [(USER, "the story")]
    assert fake.audio == [(USER, urls[0]), (USER, urls[1])]


def test_long_reply_goes_out_in_parts(monkeypatch):
    fake = run(monkeypatch, Canned(reply="\n\n".join(["p" * 3000] * 3)))
    assert [len(b) for _, b in fake.sent] == [3000, 3000, 3000]


def test_empty_reply_sends_nothing(monkeypatch):
    assert run(monkeypatch, Canned(reply="  ")).sent == []


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


async def test_cloud_sender_sends_audio_by_link(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "fake-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "100000000000001")
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", USER)
    seen = _fake_graph(monkeypatch)
    await CloudApiSender().send_audio(USER, "https://audio.example/1.mp3")
    body = json.loads(seen[0].content)
    assert body["type"] == "audio" and body["audio"] == {"link": "https://audio.example/1.mp3"}


async def test_network_error_on_send_is_logged_not_raised(monkeypatch, caplog):
    monkeypatch.setenv("WHATSAPP_TOKEN", "fake-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "100000000000001")
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", USER)

    def boom(req):
        raise httpx.ConnectTimeout("slow", request=req)

    real = httpx.AsyncClient
    monkeypatch.setattr(
        sender_mod.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(boom), **kw),
    )
    await CloudApiSender().send_text(USER, "hello")
    assert "send failed: ConnectTimeout" in caplog.text


def test_split_keeps_short_replies_whole():
    assert split("hello") == ["hello"]
    assert split("") == [""]


def test_split_breaks_at_paragraphs_then_lines_then_spaces():
    days = "\n\n".join(f"Day {i}: " + "stop, " * 30 for i in range(1, 6))
    parts = split(days, limit=400)
    assert all(len(p) <= 400 for p in parts) and len(parts) > 1
    assert all(p.startswith("Day ") for p in parts)  # whole days per message
    assert split("a\nb c", limit=3) == ["a", "b c"]
    assert split("aaaa bbbb", limit=6) == ["aaaa", "bbbb"]
    assert split("x" * 10, limit=4) == ["xxxx", "xxxx", "xx"]


def test_health_reports_the_deployed_version(bot, monkeypatch):
    client, _ = bot
    monkeypatch.delenv("GIT_SHA", raising=False)
    assert client.get("/health").json() == {"ok": True, "version": "dev"}
    monkeypatch.setenv("GIT_SHA", "abc1234")
    assert client.get("/health").json() == {"ok": True, "version": "abc1234"}


def test_split_never_sends_empty_or_padded_parts():
    assert split("\n\n" + "a" * 12, limit=10) == ["aaaaaaaaaa", "aa"]
    assert split("  " + "a" * 12 + "  ", limit=10) == ["aaaaaaaaaa", "aa"]
    assert split("abc\n\n\n\ndef", limit=4) == ["abc", "def"]
