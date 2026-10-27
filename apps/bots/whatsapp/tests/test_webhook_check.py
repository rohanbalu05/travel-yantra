import io
import json
import urllib.error

from app import webhook_check
from app.webhook_check import check

TOKEN = "fake-token"


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener(body: dict, status: int = 200, seen=None):
    def open_(req, timeout):
        if seen is not None:
            seen.append(req)
        raw = json.dumps(body).encode()
        if status != 200:
            raise urllib.error.HTTPError(req.full_url, status, "err", {}, io.BytesIO(raw))
        return Resp(raw)

    return open_


def test_lists_subscribed_apps_with_a_get():
    seen = []
    body = {"data": [{"whatsapp_business_api_data": {"id": "700000000000001", "name": "TY"}}]}
    ok, line = check(TOKEN, "200000000000001", opener(body, seen=seen))
    assert ok and line == "subscribed apps: 1 ['700000000000001']"
    [req] = seen
    assert req.get_method() == "GET" and req.full_url.endswith("/200000000000001/subscribed_apps")
    assert req.get_header("Authorization") == f"Bearer {TOKEN}"


def test_no_subscribed_app_fails():
    assert check(TOKEN, "1", opener({"data": []})) == (False, "subscribed apps: 0 []")


def test_graph_error_shows_codes_only():
    err = {
        "error": {"message": "token for 15550001111 expired", "type": "OAuthException", "code": 190}
    }
    ok, line = check(TOKEN, "1", opener(err, status=401))
    assert not ok and line == "failed: HTTP 401 code=190 subcode=None type=OAuthException"


def test_main_needs_both_env_vars(monkeypatch, capsys):
    monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_WABA_ID", raising=False)
    assert webhook_check.main() == 1
    assert "unset" in capsys.readouterr().out
