import os

import pytest

from core import fakes
from core.trips import MemoryStore, PgStore

GOA = fakes.sample("goa_family.json")


def roundtrip(store):
    a = store.save(GOA, owner="sample-owner")
    b = store.save(GOA, revised_from=a.id)
    assert a.id != b.id and a.share_token != b.share_token and len(a.share_token) >= 20
    assert store.get(a.id).itinerary == GOA and store.get(a.id).owner == "sample-owner"
    assert store.by_share_token(b.share_token).id == b.id and store.get(b.id).revised_from == a.id
    assert store.get("missing") is None and store.by_share_token("missing") is None
    # Old revised_from chains list only their newest trip.
    assert [t.id for t in store.by_owner("sample-owner")] == [a.id]
    c = store.save(GOA, owner="sample-owner", revised_from=a.id)
    assert [t.id for t in store.by_owner("sample-owner")] == [c.id]
    # A revise is a new version of the same trip: same id and token, claimed by an owner when it had none.
    lighter = GOA.model_copy(update={"warnings": ["lighter"]})
    v2 = store.update(b.id, lighter, owner="sample-owner")
    assert (v2.id, v2.share_token, v2.version, v2.owner) == (b.id, b.share_token, 2, "sample-owner")
    assert store.by_share_token(b.share_token).itinerary.warnings == ["lighter"] and v2.updated_at
    assert store.update(b.id, GOA, owner="someone-else").owner == "sample-owner"
    assert [t.id for t in store.by_owner("sample-owner")] == [b.id, c.id]  # most recently changed first
    assert store.update("missing", GOA) is None


def test_memory_store():
    roundtrip(MemoryStore())


def test_memory_store_forgets_the_oldest_past_its_limit():
    store = MemoryStore(limit=2)
    first = store.save(GOA)
    store.save(GOA)
    store.save(GOA)
    assert store.get(first.id) is None


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set")
def test_postgres_store_and_migration_is_idempotent():
    url = os.environ["DATABASE_URL"]
    PgStore(url)  # applies the migration
    roundtrip(PgStore(url))  # applies it again, then round-trips


def test_only_its_maker_may_change_a_trip_without_an_owner():
    import json

    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    maker, other = {"X-Client-Id": "sample-browser-maker-0001"}, {"X-Client-Id": "sample-browser-other-0002"}
    body = GOA.request.model_dump(mode="json")
    lines = client.post("/plan", json=body, headers=maker).text.splitlines()
    done = [json.loads(x[6:]) for x in lines if x.startswith("data: ")][-1]
    pid = done["plan_id"]
    r = client.post(f"/plan/{pid}/revise", json={"intent": "rain"}, headers=other)
    assert r.status_code == 403 and r.json()["detail"].startswith("Only the browser or chat that made this plan")
    assert client.get(f"/plan/{pid}", headers=other).status_code == 403
    assert client.get(f"/plan/{pid}").status_code == 403 and client.delete(f"/plan/{pid}", headers=other).status_code == 403
    assert client.get(f"/trips/{done['share_token']}").status_code == 200  # the share link still shows it
    assert client.post(f"/plan/{pid}/revise", json={"intent": "rain"}, headers=maker).status_code == 200
    # Signed in later on the same browser: the browser id sent with the sign-in still counts.
    assert client.get(f"/plan/{pid}", headers=maker).status_code == 200
    assert client.get("/plan/not-a-plan").json() == {"detail": "This plan was not found. It may have been deleted."}
    # Deleting the browser's data takes its trips, kept or not.
    assert client.delete("/me", headers=maker).status_code == 202 and client.get(f"/trips/{done['share_token']}").status_code == 404
    # A plan made without any id (older clients) stays the plan_id holder's.
    lines = client.post("/plan", json=body).text.splitlines()
    anon = [json.loads(x[6:]) for x in lines if x.startswith("data: ")][-1]["plan_id"]
    assert client.get(f"/plan/{anon}", headers=other).status_code == 200


def test_a_stale_revise_never_overwrites_a_newer_version():
    from core.trips import TripChanged

    store = MemoryStore()
    a = store.save(GOA)
    store.update(a.id, GOA, version=1)  # another tab saved version 2
    with pytest.raises(TripChanged):
        store.update(a.id, GOA, version=1)
    assert store.get(a.id).version == 2 and store.update(a.id, GOA, version=2).version == 3
