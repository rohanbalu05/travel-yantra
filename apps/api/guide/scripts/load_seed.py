"""Load the guide corpus into Postgres.

    cd apps/api && uv sync --all-extras
    DATABASE_URL=... uv run python -m guide.scripts.load_seed [--reembed]

Applies guide/migrations/*.sql (idempotent), upserts the seed data, embeds rows
that lack a vector with multilingual-e5-small (downloaded on first use). Safe to
re-run. EMBEDDER=fake writes vectors only the fake can search, so it is refused
unless --allow-fake says this database is a throwaway.
"""

from __future__ import annotations

import argparse
import os

import psycopg

from guide.retrieval.seed import apply_migrations, load_seed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reembed", action="store_true")
    parser.add_argument("--allow-fake", action="store_true")
    args = parser.parse_args()
    if os.environ.get("EMBEDDER") == "fake" and not args.allow_fake:
        raise SystemExit("EMBEDDER=fake would store fake vectors; unset it or pass --allow-fake")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        apply_migrations(conn)
        for table, n in load_seed(conn, reembed=args.reembed).items():
            print(f"{table}: {n}")


if __name__ == "__main__":
    main()
