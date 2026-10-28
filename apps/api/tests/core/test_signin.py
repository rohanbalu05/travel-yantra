import json
import os

import pytest
from fastapi.testclient import TestClient

from core import accounts, auth, fakes
from main import app
from ty_contracts import Me

client = TestClient(app)
BROWSER = "sample-browser-signin-0001"
MYSURU = fakes.sample("mysuru_weekend.json").request.model_dump(mode="json")
TOKENS = {"good-token": auth.Claims("fb:sample-sub-1", "arjun.sample@example.com", "Arjun Rao"),
          "other-token": auth.Claims("fb:sample-sub-2", None, None)}


@pytest.fixture(autouse=True)
def fake_verifier(monkeypatch):
    """No network: tokens are looked up in TOKENS; anything else is rejected like a bad signature."""
    def verify(token):
        if token not in TOKENS:
            raise auth.AuthError("invalid or expired sign-in token")
        return TOKENS[token]

    monkeypatch.setattr(auth, "verify", verify)


def bearer(token, browser=None):
    h = {"Authorization": f"Bearer {token}"}
    return {**h, "X-Client-Id": browser} if browser else h


def done(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")][-1]


def test_a_signed_in_account_is_stable_and_carries_name_and_email():
    me = Me.model_validate(client.get("/me", headers=bearer("good-token")).json())
    assert (me.uid, me.email, me.name) == ("fb:sample-sub-1", "arjun.sample@example.com", "Arjun Rao")
    assert client.get("/me", headers=bearer("good-token")).json()["uid"] == me.uid


@pytest.mark.parametrize("headers", [{"Authorization": "Bearer nope"}, {"Authorization": "Basic abc"},
                                     {"Authorization": "Bearer nope", "X-Client-Id": BROWSER}])
def test_a_bad_token_is_401_and_never_falls_back_to_the_browser_id(headers):
    assert client.get("/me", headers=headers).status_code == 401
    assert client.post("/plan", json=MYSURU, headers=headers).status_code == 401


def test_first_sign_in_moves_the_browser_trips_ratings_and_consents_once(memory_accounts):
    anon = {"X-Client-Id": BROWSER}
    client.put("/me/consents", json={"plan_history": True}, headers=anon)
    trip = done(client.post("/plan", json=MYSURU, headers=anon))
    client.post("/ratings", json={"plan_id": trip["plan_id"], "score": 5}, headers=anon)

    me = Me.model_validate(client.get("/me", headers=bearer("good-token", BROWSER)).json())
    assert me.consents.plan_history  # the browser's choice came along
    assert [t["plan_id"] for t in client.get("/me/trips", headers=bearer("good-token")).json()] == [trip["plan_id"]]
    assert [r.uid for r in memory_accounts.ratings] == ["fb:sample-sub-1"]
    # Signed out, the browser id still works; its old data now belongs to the account.
    assert client.get("/me/trips", headers=anon).json() == []
    assert not Me.model_validate(client.get("/me", headers=anon).json()).consents.plan_history
    # Linking happens once: a later anonymous trip on the same browser is not pulled in on the next call.
    client.put("/me/consents", json={"plan_history": True}, headers=anon)
    later = done(client.post("/plan", json=MYSURU, headers=anon))
    client.get("/me", headers=bearer("good-token", BROWSER))
    assert later["plan_id"] not in [t["plan_id"] for t in client.get("/me/trips", headers=bearer("good-token")).json()]


def test_an_account_keeps_its_own_consents_when_a_browser_joins():
    client.put("/me/consents", json={"analytics": True, "plan_history": False}, headers=bearer("other-token"))
    client.put("/me/consents", json={"plan_history": True}, headers={"X-Client-Id": BROWSER})
    me = Me.model_validate(client.get("/me", headers=bearer("other-token", BROWSER)).json())
    assert me.consents.analytics and not me.consents.plan_history


def test_a_signed_in_account_keeps_plan_history_until_it_turns_it_off():
    me = Me.model_validate(client.get("/me", headers=bearer("good-token")).json())
    assert me.consents.plan_history and not me.consents.location and me.consents_updated_at is None
    trip = done(client.post("/plan", json=MYSURU, headers=bearer("good-token")))
    assert [t["plan_id"] for t in client.get("/me/trips", headers=bearer("good-token")).json()] == [trip["plan_id"]]
    client.put("/me/consents", json={"plan_history": False}, headers=bearer("good-token"))
    assert client.get("/me/trips", headers=bearer("good-token")).json() == []
    done(client.post("/plan", json=MYSURU, headers=bearer("good-token")))
    assert client.get("/me/trips", headers=bearer("good-token")).json() == []


def test_signed_in_plans_and_delete_me(memory_accounts):
    client.put("/me/consents", json={"plan_history": True}, headers=bearer("good-token"))
    trip = done(client.post("/plan", json=MYSURU, headers=bearer("good-token", BROWSER)))
    assert client.get("/me/trips", headers=bearer("good-token")).json()[0]["plan_id"] == trip["plan_id"]
    r = client.delete("/me", headers=bearer("good-token"))
    assert r.status_code == 202 and client.get(f"/trips/{trip['share_token']}").status_code == 404
    assert not accounts.get_accounts().linked(BROWSER)


def test_without_a_project_sign_in_is_off(monkeypatch):
    monkeypatch.undo()  # the real verifier
    monkeypatch.delenv("TY_FIREBASE_PROJECT_ID", raising=False)
    r = client.get("/me", headers={"Authorization": "Bearer anything"})
    assert r.status_code == 401 and r.json()["detail"] == "sign-in is not configured"
    assert client.get("/me", headers={"X-Client-Id": BROWSER}).status_code == 200


def test_real_verifier_rejects_a_token_that_is_not_a_jwt(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setenv("TY_FIREBASE_PROJECT_ID", "sample-project")
    monkeypatch.setattr(auth, "certs", lambda: {})  # no network
    with pytest.raises(auth.AuthError):
        auth.verify("not-a-jwt")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set")
def test_postgres_link_moves_once():
    from core.accounts import PgAccounts, Rating
    from core.trips import PgStore
    from ty_contracts import ConsentsUpdate

    url, anon, uid = os.environ["DATABASE_URL"], "sample-pg-browser-link-01", "fb:sample-pg-sub"
    acc, store = PgAccounts(url), PgStore(url)
    for x in (anon, uid):
        acc.delete(x)
        store.delete_owner(x)
    acc.set_consents(anon, ConsentsUpdate(plan_history=True))
    store.save(fakes.sample("goa_family.json"), owner=anon)
    acc.add_rating(Rating(anon, None, 4, None, "en"))
    assert not acc.linked(anon)
    assert store.reassign_owner(anon, uid) == 1 and acc.link(anon, uid) == 2  # 1 rating + consents
    assert acc.linked(anon) and acc.link(anon, uid) is None
    assert acc.pending(anon, uid)  # claimed; this test moved the trips by hand, so mark them moved
    acc.mark_moved(anon)
    assert not acc.pending(anon, uid)
    assert acc.consents(uid)[0].plan_history and len(store.by_owner(uid)) == 1
    acc.delete(uid)
    store.delete_owner(uid)
    assert not acc.linked(anon)


def test_cert_outage_is_503_without_cache_and_uses_the_cache_otherwise(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setenv("TY_FIREBASE_PROJECT_ID", "sample-project")

    def down():
        raise OSError("network down")

    monkeypatch.setattr(auth, "_fetch_certs", down)
    monkeypatch.setattr(auth, "_certs", {})
    with pytest.raises(auth.AuthUnavailable):
        auth.certs()
    assert client.get("/me", headers={"Authorization": "Bearer x.y.z"}).status_code == 503
    monkeypatch.setattr(auth, "_certs", {"kid": "cert"})
    monkeypatch.setattr(auth, "_certs_at", -10_000.0)  # stale
    assert auth.certs() == {"kid": "cert"}


def test_a_second_account_cannot_claim_an_already_linked_browser(memory_accounts):
    anon = {"X-Client-Id": BROWSER}
    client.put("/me/consents", json={"plan_history": True}, headers=anon)
    done(client.post("/plan", json=MYSURU, headers=anon))
    client.get("/me", headers=bearer("good-token", BROWSER))
    assert memory_accounts.link(BROWSER, "fb:sample-sub-2") is None
    client.get("/me", headers=bearer("other-token", BROWSER))
    assert client.get("/me/trips", headers=bearer("other-token")).json() == []
    assert len(client.get("/me/trips", headers=bearer("good-token")).json()) == 1


def test_a_failed_move_after_the_claim_is_retried_on_the_next_signed_in_call(monkeypatch, memory_trips):
    anon = {"X-Client-Id": BROWSER}
    client.put("/me/consents", json={"plan_history": True}, headers=anon)
    trip = done(client.post("/plan", json=MYSURU, headers=anon))
    real = memory_trips.reassign_owner

    def broken(old, new):
        raise RuntimeError("database went away")

    monkeypatch.setattr(memory_trips, "reassign_owner", broken)
    client.get("/me", headers=bearer("good-token", BROWSER))  # claimed, but the trips did not move
    assert client.get("/me/trips", headers=bearer("good-token")).json() == []
    assert accounts.get_accounts().pending(BROWSER, "fb:sample-sub-1")
    monkeypatch.setattr(memory_trips, "reassign_owner", real)
    client.get("/me", headers=bearer("good-token", BROWSER))  # retried
    assert [t["plan_id"] for t in client.get("/me/trips", headers=bearer("good-token")).json()] == [trip["plan_id"]]
    assert not accounts.get_accounts().pending(BROWSER, "fb:sample-sub-1")
