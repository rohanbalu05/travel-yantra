import pytest

from core import accounts, trips


@pytest.fixture(autouse=True)
def memory_trips():
    """Core tests use a fresh in-memory trip store; test_trips.py covers Postgres on its own."""
    store = trips.MemoryStore()
    trips.set_store(store)
    yield store
    trips.set_store(None)


@pytest.fixture(autouse=True)
def memory_accounts():
    """Core tests use a fresh in-memory account store; test_accounts.py covers Postgres on its own."""
    store = accounts.MemoryAccounts()
    accounts.set_accounts(store)
    yield store
    accounts.set_accounts(None)
