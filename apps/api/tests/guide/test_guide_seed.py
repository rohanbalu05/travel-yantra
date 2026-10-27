"""Seed data checks. The counts and references need no database."""

from guide.retrieval.seed import chunk_rows, load_pois, poi_row

CATEGORIES = {"temple", "monument", "museum", "nature", "viewpoint", "market", "food", "experience"}


def test_seed_counts() -> None:
    # The v1 database also held 23 drafted Mangalore POIs and 54 retired chunks
    # that were never in git; the committed seed is 112 POIs, 288 chunks, 22 legends.
    # Built corridors (data/corridor/, from Wikimedia) come on top: Goa adds 18 and 108.
    data = load_pois()
    rows, retags = chunk_rows()
    karnataka = [p for p in data["pois"] if p["city"] != "Goa"]
    assert len(karnataka) == 112 and len(data["pois"]) == 112 + 18
    assert len(rows) == 288 + 108
    assert len({(r["city"], r["title"]) for r in rows}) == len(rows)
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


def test_corridor_places_are_inside_their_region() -> None:
    # A Wikimedia namesake abroad once put Fontainhas in Cape Verde and Reis Magos in Brazil.
    from guide.scripts.build_corridor import BBOX, in_bbox, pick_coords

    goa = [p for p in load_pois()["pois"] if p["city"] == "Goa"]
    assert goa and all(in_bbox("goa", p["lat"], p["lng"]) for p in goa)
    assert not in_bbox("goa", 17.188, -25.104) and set(BBOX) == {"goa"}
    # Wikipedia wins when Wikidata is far off or missing; otherwise Wikidata stays.
    assert pick_coords((15.50772, 73.80312), (15.3958, 73.9678)) == (15.3958, 73.9678)
    assert pick_coords((15.5009, 73.9116), (15.5010, 73.9110)) == (15.5009, 73.9116)
    assert pick_coords((None, None), (15.5, 73.9)) == (15.5, 73.9)
    assert pick_coords((15.5, 73.9), (None, None)) == (15.5, 73.9)
