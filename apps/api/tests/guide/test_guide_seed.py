"""Seed data checks. The counts and references need no database."""

from guide.retrieval.seed import chunk_rows, load_pois, poi_row

CATEGORIES = {"temple", "monument", "museum", "nature", "viewpoint", "market", "food", "experience"}


def test_seed_counts() -> None:
    # The v1 database also held 23 drafted Mangalore POIs and 54 retired chunks
    # that were never in git; the committed seed is 112 POIs, 288 chunks, 22 legends.
    data = load_pois()
    rows, retags = chunk_rows()
    assert len(data["pois"]) == 112
    assert len(rows) == 288
    assert len({(r["city"], r["title"]) for r in rows}) == 288
    assert sum(bool(r.get("is_legend")) for r in rows) == 22
    assert len(retags) == 39


def test_pois_are_valid_and_unique() -> None:
    pois = load_pois()["pois"]
    for p in pois:
        assert p["category"] in CATEGORIES, p["name"]
        assert poi_row(p)["trust"] in {"verified", "draft"}
    assert len({p["name"] for p in pois}) == len(pois)  # edges use bare names


def test_references_resolve() -> None:
    data = load_pois()
    names = {p["name"] for p in data["pois"]}
    cities = {p["city"] for p in data["pois"]}
    assert all(e["from"] in names and e["to"] in names for e in data["edges"])
    assert all(
        leg["from"] in cities and leg["to"] in cities for leg in data["intercity_legs"]
    )
    for r in chunk_rows()[0]:
        assert not r["poi"] or (r["poi"], r["city"]) in {(p["name"], p["city"]) for p in data["pois"]}
