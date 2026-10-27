import json
import os

import pytest
from fastapi.testclient import TestClient

from core import fakes
from core.accounts import PgAccounts, Rating
from core.trips import PgStore
from main import app
from ty_contracts import ConsentsUpdate, Me, TripSummary

client = TestClient(app)
ME = {"X-Client-Id": "sample-browser-0001-aaaa"}
OTHER = {"X-Client-Id": "sample-browser-0002-bbbb"}
GOA = fakes.sample("goa_family.json").request.model_dump(mode="json")
MYSURU = fakes.sample("mysuru_weekend.json").request.model_dump(mode="json")


def done(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")][-1]


@pytest.mark.parametrize("headers", [{}, {"X-Client-Id": "short"}, {"X-Client-Id": "has spaces in it, sadly!"}])
def test_me_endpoints_need_a_valid_client_id(headers):
    assert client.get("/me", headers=headers).status_code == 401
    assert client.put("/me/consents", json={}, headers=headers).status_code == 401
    assert client.delete("/me", headers=headers).status_code == 401
    assert client.get("/me/trips", headers=headers).status_code == 401


def test_consents_start_off_and_update_one_purpose_at_a_time():
    me = Me.model_validate(client.get("/me", headers=ME).json())
    assert me.uid == ME["X-Client-Id"] and me.email is None and me.consents_updated_at is None
    assert not (me.consents.plan_history or me.consents.location or me.consents.analytics)
    me = Me.model_validate(client.put("/me/consents", json={"plan_history": True}, headers=ME).json())
    assert me.consents.plan_history and not me.consents.location and me.consents_updated_at is not None
    me = Me.model_validate(client.put("/me/consents", json={"analytics": True}, headers=ME).json())
    assert me.consents.plan_history and me.consents.analytics  # earlier choices kept
    assert not Me.model_validate(client.get("/me", headers=OTHER).json()).consents.plan_history


def test_plans_are_listed_only_with_the_plan_history_consent():
    client.post("/plan", json=MYSURU, headers=ME)  # no consent yet: not linked
    assert client.get("/me/trips", headers=ME).json() == []
    client.put("/me/consents", json={"plan_history": True}, headers=ME)
    first = done(client.post("/plan", json=MYSURU, headers=ME))
    second = done(client.post("/plan", json=GOA, headers=ME))
    revised = done(client.post(f"/plan/{second['plan_id']}/revise", json={"intent": "rain"}, headers=ME))
    trips = [TripSummary.model_validate(t) for t in client.get("/me/trips", headers=ME).json()]
    assert [t.plan_id for t in trips] == [revised["plan_id"], second["plan_id"], first["plan_id"]]  # newest first
    assert trips[-1].title == "Mysuru, 31 Oct – 01 Nov" and trips[-1].share_token == first["share_token"]
    assert client.get("/me/trips", headers=OTHER).json() == []
    done(client.post("/plan", json=MYSURU))  # no header: never linked
    assert len(client.get("/me/trips", headers=ME).json()) == 3


def test_ratings_work_with_or_without_an_id(memory_accounts):
    assert client.post("/ratings", json={"score": 5, "comment": "Lovely day plan", "lang": "kn"}).json() == {"ok": True}
    r = client.post("/ratings", json={"plan_id": "p1", "score": 4}, headers=ME)
    assert r.status_code == 201
    assert [(x.uid, x.score) for x in memory_accounts.ratings] == [(None, 5), (ME["X-Client-Id"], 4)]
    assert client.post("/ratings", json={"score": 9}).status_code == 422


def test_delete_me_removes_everything_for_that_id_and_nothing_else(memory_accounts):
    client.put("/me/consents", json={"plan_history": True}, headers=ME)
    mine = done(client.post("/plan", json=MYSURU, headers=ME))
    client.put("/me/consents", json={"plan_history": True}, headers=OTHER)
    theirs = done(client.post("/plan", json=MYSURU, headers=OTHER))
    client.post("/ratings", json={"score": 3}, headers=ME)
    client.post("/ratings", json={"score": 2})

    r = client.delete("/me", headers=ME)
    assert r.status_code == 202 and r.json() == {"deleted": True, "items": 3}  # 1 trip, consents, 1 rating
    assert client.get("/me/trips", headers=ME).json() == []
    assert client.get(f"/trips/{mine['share_token']}").status_code == 404
    assert not Me.model_validate(client.get("/me", headers=ME).json()).consents.plan_history
    assert client.get(f"/trips/{theirs['share_token']}").status_code == 200
    assert [x.uid for x in memory_accounts.ratings] == [None]
    assert client.delete("/me", headers=ME).json() == {"deleted": True, "items": 0}


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set")
def test_postgres_accounts_and_owned_trips():
    url = os.environ["DATABASE_URL"]
    uid = "sample-pg-browser-0003"
    acc, store = PgAccounts(url), PgStore(url)
    acc.delete(uid)
    store.delete_owner(uid)
    consents, _ = acc.set_consents(uid, ConsentsUpdate(plan_history=True))
    assert consents.plan_history and acc.consents(uid)[0].plan_history
    goa = fakes.sample("goa_family.json")
    a = store.save(goa, owner=uid)
    b = store.save(goa, owner=uid, revised_from=a.id)
    stranger = store.save(goa, revised_from=a.id)  # someone else's revision of my trip
    assert [t.id for t in store.by_owner(uid)] == [b.id, a.id]
    acc.add_rating(Rating(uid, a.id, 5, None, "en"))
    assert store.delete_owner(uid) + acc.delete(uid) == 4
    assert store.by_owner(uid) == [] and store.get(stranger.id).revised_from is None
