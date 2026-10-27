import pytest

from core import trips


@pytest.fixture(autouse=True)
def memory_trips():
    """Core tests use a fresh in-memory trip store; test_trips.py covers Postgres on its own."""
    store = trips.MemoryStore()
    trips.set_store(store)
    yield store
    trips.set_store(None)
