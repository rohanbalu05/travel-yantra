"""Build corridor corpus files from Wikimedia (card #22). Goa first.

    cd apps/api && uv run python -m guide.scripts.build_corridor [goa]

Which places, their category and a typical visit length are editorial choices,
listed below. Everything else (coordinates, native names, every paragraph of
text) comes from Wikipedia and Wikidata, with the page URL as the source. Opening
hours and fees are not in Wikimedia, so these POIs are marked draft and tagged
hours-unverified and fee-unverified until Places or a person fills them.

Writes data/corridor/<region>_pois.json and <region>_chunks.json, which the seed
loader and the planner pick up. Wikimedia is free; the call count is printed.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date

from guide.retrieval.seed import DATA
from guide.wiki import WikiClient, paragraphs

OUT = DATA / "corridor"
MAX_CHUNKS = 6  # per place: the lead and the history, not the whole article
PAUSE_S = 0.3  # between live requests

#: (Wikipedia title, display name or None, category, minutes, district, popularity)
REGIONS = {
    "goa": {
        "city": "Goa",
        "city_pages": ["Goa", "Old Goa", "Panaji"],
        "places": [
            ("Basilica of Bom Jesus", None, "monument", 60, "North Goa", 5),
            ("Se Cathedral", None, "monument", 45, "North Goa", 5),
            ("Church and Convent of St. Francis of Assisi", "Church of St. Francis of Assisi", "monument", 30, "North Goa", 4),
            ("Fontainhas", None, "experience", 90, "North Goa", 5),
            ("Our Lady of the Immaculate Conception Church, Goa", "Immaculate Conception Church, Panaji", "monument", 30, "North Goa", 4),
            ("Fort Aguada", None, "monument", 75, "North Goa", 5),
            ("Forte dos Reis Magos", "Reis Magos Fort", "monument", 60, "North Goa", 4),
            ("Chapora Fort", None, "viewpoint", 60, "North Goa", 4),
            ("Calangute", "Calangute Beach", "nature", 120, "North Goa", 4),
            ("Anjuna", "Anjuna Beach", "nature", 120, "North Goa", 4),
            ("Palolem Beach", None, "nature", 150, "South Goa", 5),
            ("Dudhsagar Falls", None, "nature", 240, "South Goa", 5),
            ("Mangueshi Temple", None, "temple", 45, "North Goa", 4),
            ("Shanta Durga Temple", "Shantadurga Temple", "temple", 45, "North Goa", 4),
            ("Goa State Museum", None, "museum", 60, "North Goa", 3),
            ("Naval Aviation Museum (Goa)", "Naval Aviation Museum", "museum", 75, "South Goa", 3),
            ("Cabo de Rama Fort", None, "viewpoint", 60, "South Goa", 3),
            ("Divar", "Divar Island", "nature", 120, "North Goa", 3),
        ],
    },
}


def build(region: str, wiki: WikiClient) -> tuple[list[dict], list[dict], list[str]]:
    spec = REGIONS[region]
    city, today = spec["city"], date.today().isoformat()
    pois, chunks, skipped = [], [], []

    def add_chunks(poi_name: str | None, page: str) -> int:
        url, sections = wiki.sections(page)
        time.sleep(PAUSE_S)
        n = 0
        for heading, body in sections:
            for i, para in enumerate(paragraphs(body)):
                if n >= MAX_CHUNKS:
                    return n
                n += 1
                label = page if heading == "Introduction" else f"{page}: {heading}"
                chunks.append({
                    "poi": poi_name, "city": city, "lang": "en",
                    "title": label if i == 0 else f"{label} ({i + 1})",
                    "body": para, "chunk_type": "fact", "is_legend": False,
                    "source_name": "Wikipedia (CC BY-SA)", "source_url": url, "last_verified": today,
                })  # fmt: skip
        return n

    for title, display, category, minutes, district, popularity in spec["places"]:
        data = wiki.labels(title)
        time.sleep(PAUSE_S)
        lat, lng = data["lat"], data["lng"]
        if lat is None:
            s = wiki.summary(title)
            time.sleep(PAUSE_S)
            lat, lng = s["lat"], s["lng"]
        if lat is None or not data["qid"]:
            skipped.append(f"{title}: no Wikidata item or coordinates")
            continue
        name = display or data["labels"].get("en") or title
        names = {k: v for k, v in data["labels"].items() if k != "en"}
        pois.append({
            "name": name, "name_kn": names.get("kn"), "names": names, "city": city,
            "district": district, "lat": round(lat, 5), "lng": round(lng, 5),
            "category": category, "tags": ["hours-unverified", "fee-unverified"],
            "typical_dwell_min": minutes, "opens": None, "closes": None, "closed_on": [],
            "popularity": popularity, "elderly_friendly": True, "trust": "draft",
            "source_url": f"https://www.wikidata.org/wiki/{data['qid']}", "last_verified": today,
        })  # fmt: skip
        if not add_chunks(name, title):
            skipped.append(f"{title}: no prose paragraphs")
    for page in spec["city_pages"]:
        add_chunks(None, page)
    return pois, chunks, skipped


def main(regions: list[str]) -> None:
    wiki = WikiClient()
    OUT.mkdir(exist_ok=True)
    for region in regions:
        pois, chunks, skipped = build(region, wiki)
        note = (f"Built by guide/scripts/build_corridor.py from Wikipedia and Wikidata on "
                f"{date.today().isoformat()}. Text is CC BY-SA; each chunk cites its page.")  # fmt: skip
        (OUT / f"{region}_pois.json").write_text(
            json.dumps({"_notes": note, "pois": pois}, ensure_ascii=False, indent=1), encoding="utf-8")
        (OUT / f"{region}_chunks.json").write_text(
            json.dumps({"note": note, "chunks": chunks}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{region}: {len(pois)} places, {len(chunks)} chunks; skipped: {skipped or 'none'}")
    print(f"Wikimedia requests: {wiki.calls}")


if __name__ == "__main__":
    main(sys.argv[1:] or list(REGIONS))
