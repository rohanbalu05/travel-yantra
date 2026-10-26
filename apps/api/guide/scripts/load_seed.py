"""Load the guide corpus into Postgres.

    cd apps/api && DATABASE_URL=... python -m guide.scripts.load_seed [--reembed]

Applies guide/migrations/*.sql (idempotent), upserts the seed data, embeds rows
that lack a vector. Set EMBEDDER=fake to skip the local model.
"""

from __future__ import annotations

import argparse
import os

import psycopg

from guide.retrieval.seed import apply_migrations, load_seed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reembed", action="store_true")
    args = parser.parse_args()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        apply_migrations(conn)
        for table, n in load_seed(conn, reembed=args.reembed).items():
            print(f"{table}: {n}")


if __name__ == "__main__":
    main()
