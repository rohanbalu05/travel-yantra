import os
import sys
from pathlib import Path

import pytest

# apps/api on sys.path so `import guide` works however pytest is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
# Tests never load the model or touch the network.
os.environ["EMBEDDER"] = "fake"


@pytest.fixture(scope="session")
def db():
    """A seeded pgvector database, or skip when DATABASE_URL is unset."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    import psycopg

    from guide.retrieval.seed import apply_migrations, load_seed

    with psycopg.connect(url, autocommit=True) as conn:
        apply_migrations(conn)
        load_seed(conn)
        yield conn
