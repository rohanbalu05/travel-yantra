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
