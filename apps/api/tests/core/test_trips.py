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
