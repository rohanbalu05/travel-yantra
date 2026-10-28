"""Build corridor corpus files from Wikimedia (card #22): Goa, then Kerala (Kochi, Munnar,
Alleppey) and the Golden Triangle (Delhi, Agra, Jaipur) for HQ P8.

    cd apps/api && uv run python -m guide.scripts.build_corridor [goa kochi ...]

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
from guide.scripts.enrich_places import km
from guide.wiki import WikiClient, paragraphs

OUT = DATA / "corridor"
MAX_CHUNKS = 6  # per place: the lead and the history, not the whole article
#: The best-known places carry a 5-minute Katha (HQ P8: Taj Mahal, Red Fort...), which needs
#: more facts than a lead and a history paragraph.
MAX_CHUNKS_TOP = 12
PAUSE_S = 0.3  # between live requests

#: (Wikipedia title, display name or None, category, minutes, district, popularity)
#: Where a region's places may be: a page that resolves to a namesake abroad
#: ("Fontainhas" is in Cape Verde, "Forte dos Reis Magos" in Brazil) is skipped.
BBOX = {  # lat min, lat max, lng min, lng max
    "goa": (14.85, 15.85, 73.65, 74.35),
    "kochi": (9.80, 10.25, 76.10, 76.50),
    "munnar": (9.75, 10.40, 76.85, 77.35),
    "alleppey": (9.15, 9.95, 76.20, 76.65),  # Vembanad and the backwaters reach 9.9
    "delhi": (28.40, 28.90, 76.80, 77.40),
    "agra": (26.95, 27.35, 77.55, 78.20),
    "jaipur": (26.70, 27.10, 75.60, 76.15),  # Galtaji is in the hills east
}
#: Wikidata and Wikipedia disagreeing by more than this: Wikipedia's coordinates win
#: (Wikidata put Shantadurga Temple 23 km off, near Panaji).
MAX_DISAGREE_KM = 3.0
#: The temple page has no coordinates and Wikidata's are 8 km off; the village's are right.
COORDS_PAGE = {"Mangueshi Temple": "Mangueshi"}

REGIONS = {
    "goa": {
        "city": "Goa",
        "city_pages": ["Goa", "Old Goa", "Panaji"],
        "places": [
            ("Basilica of Bom Jesus", None, "monument", 60, "North Goa", 5),
            ("Se Cathedral", None, "monument", 45, "North Goa", 5),
            ("Church and Convent of St. Francis of Assisi", "Church of St. Francis of Assisi", "monument", 30, "North Goa", 4),
            ("Fontainhas (quarter)", "Fontainhas", "experience", 90, "North Goa", 5),
            ("Our Lady of the Immaculate Conception Church, Goa", "Immaculate Conception Church, Panaji", "monument", 30, "North Goa", 4),
            ("Fort Aguada", None, "monument", 75, "North Goa", 5),
            ("Reis Magos", "Reis Magos Fort", "monument", 60, "North Goa", 4),
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
    "kochi": {
        "city": "Kochi",
        "city_pages": ["Kochi", "Mattancherry"],
        "places": [
            ("Fort Kochi", None, "experience", 180, "Ernakulam", 5),
            ("Chinese fishing nets", "Chinese Fishing Nets, Fort Kochi", "experience", 30, "Ernakulam", 5),
            ("St. Francis Church, Kochi", "St. Francis Church, Fort Kochi", "monument", 30, "Ernakulam", 4),
            ("Santa Cruz Cathedral Basilica", None, "monument", 30, "Ernakulam", 4),
            ("Paradesi Synagogue", None, "monument", 30, "Ernakulam", 5),
            ("Mattancherry Palace", "Mattancherry Palace (Dutch Palace)", "museum", 60, "Ernakulam", 5),
            ("Jew Town, Kochi", "Jew Town", "market", 60, "Ernakulam", 4),
            ("Kerala Folklore Museum", None, "museum", 75, "Ernakulam", 3),
            ("Hill Palace", "Hill Palace Museum, Tripunithura", "museum", 90, "Ernakulam", 4),
            ("Marine Drive, Kochi", None, "experience", 45, "Ernakulam", 3),
            ("Bolgatty Palace", None, "monument", 45, "Ernakulam", 3),
            ("Indo-Portuguese Museum", None, "museum", 45, "Ernakulam", 3),
            ("Dutch Cemetery, Kochi", "Dutch Cemetery, Fort Kochi", "monument", 20, "Ernakulam", 2),
            ("Cherai Beach", None, "nature", 120, "Ernakulam", 4),
            ("Mangalavanam Bird Sanctuary", None, "nature", 60, "Ernakulam", 3),
            ("Pallipuram Fort", None, "monument", 30, "Ernakulam", 2),
            ("Vasco House", None, "monument", 20, "Ernakulam", 2),
            ("Chendamangalam Synagogue", None, "monument", 30, "Ernakulam", 2),
            ("Kalady", "Kalady (Adi Shankara's birthplace)", "temple", 60, "Ernakulam", 3),
            ("Willingdon Island", None, "experience", 45, "Ernakulam", 2),
            ("Thrikkakara Temple", None, "temple", 30, "Ernakulam", 2),
        ],
    },
    "munnar": {
        "city": "Munnar",
        "city_pages": ["Munnar"],
        "places": [
            ("Eravikulam National Park", None, "nature", 180, "Idukki", 5),
            ("Anamudi", None, "viewpoint", 120, "Idukki", 4),
            ("Mattupetty Dam", "Mattupetty Dam and Lake", "nature", 60, "Idukki", 4),
            ("Kundala Dam", "Kundala Lake", "nature", 60, "Idukki", 3),
            ("Top Station", None, "viewpoint", 90, "Idukki", 4),
            ("Attukad Waterfalls", None, "nature", 45, "Idukki", 3),
            ("Lakkam Waterfalls", None, "nature", 45, "Idukki", 3),
            ("Chinnar Wildlife Sanctuary", None, "nature", 180, "Idukki", 3),
            ("Marayoor", "Marayoor (sandalwood forest and dolmens)", "experience", 150, "Idukki", 3),
            ("Meesapulimala", None, "viewpoint", 240, "Idukki", 3),
            ("Anayirangal Dam", None, "nature", 60, "Idukki", 2),
            ("Devikulam", "Devikulam and Sita Devi Lake", "nature", 90, "Idukki", 2),
            ("Kolukkumalai", "Kolukkumalai Tea Estate", "experience", 240, "Idukki", 3),
            ("Pothamedu", "Pothamedu Viewpoint", "viewpoint", 30, "Idukki", 2),
            ("Neelakurinji", None, "nature", 60, "Idukki", 3),
            ("Idukki Dam", None, "nature", 60, "Idukki", 3),
            ("Kanan Devan Hills", None, "nature", 120, "Idukki", 3),
            ("Pallivasal Hydro-Electric Project", "Pallivasal", "nature", 45, "Idukki", 2),
            ("Chinnakanal", None, "nature", 60, "Idukki", 2),
            ("Ponmudi Dam", None, "nature", 45, "Idukki", 2),
            ("Vattavada", None, "nature", 120, "Idukki", 2),
            ("Kurangani", None, "nature", 180, "Idukki", 2),
            ("Kallar, Idukki", "Kallar", "nature", 60, "Idukki", 2),
        ],
    },
    "alleppey": {
        "city": "Alleppey",
        "city_pages": ["Alappuzha", "Nehru Trophy Boat Race"],
        "places": [
            ("Kerala backwaters", "Alleppey backwaters", "experience", 240, "Alappuzha", 5),
            ("Vembanad", "Vembanad Lake", "nature", 180, "Alappuzha", 5),
            ("Kuttanad", None, "nature", 180, "Alappuzha", 4),
            ("Alappuzha Beach", "Alleppey Beach", "nature", 60, "Alappuzha", 4),
            ("Marari Beach", None, "nature", 120, "Alappuzha", 4),
            ("Ambalappuzha Sree Krishna Temple", None, "temple", 45, "Alappuzha", 4),
            ("Krishnapuram Palace", None, "museum", 60, "Alappuzha", 3),
            ("Mullakkal Rajarajeswari Temple", None, "temple", 30, "Alappuzha", 3),
            ("Kumarakom Bird Sanctuary", None, "nature", 90, "Kottayam", 4),
            ("Pathiramanal", "Pathiramanal Island", "nature", 90, "Alappuzha", 3),
            ("Revi Karunakaran Memorial Museum", None, "museum", 60, "Alappuzha", 3),
            ("St. Andrew's Basilica, Arthunkal", None, "monument", 30, "Alappuzha", 3),
            ("Champakulam", "Champakulam (St. Mary's Church)", "experience", 60, "Alappuzha", 2),
            ("Karumadikkuttan", "Karumadi Kuttan Buddha", "monument", 20, "Alappuzha", 2),
            ("Alappuzha Lighthouse", "Alleppey Lighthouse", "viewpoint", 30, "Alappuzha", 2),
            ("Haripad Sree Subrahmanya Swamy Temple", "Haripad Subramanya Temple", "temple", 30, "Alappuzha", 2),
            ("Chettikulangara Devi Temple", None, "temple", 30, "Alappuzha", 2),
            ("Kumarakom", None, "nature", 180, "Kottayam", 4),
        ],
    },
    "delhi": {
        "city": "Delhi",
        "city_pages": ["Delhi", "Old Delhi", "New Delhi"],
        "places": [
            ("Red Fort", None, "monument", 120, "Central Delhi", 5),
            ("Qutb Minar", "Qutub Minar", "monument", 90, "South Delhi", 5),
            ("Humayun's Tomb", None, "monument", 75, "South East Delhi", 5),
            ("India Gate", None, "monument", 30, "New Delhi", 5),
            ("Jama Masjid, Delhi", None, "monument", 45, "Central Delhi", 4),
            ("Lotus Temple", None, "temple", 45, "South East Delhi", 4),
            ("Akshardham (Delhi)", "Swaminarayan Akshardham, Delhi", "temple", 150, "East Delhi", 4),
            ("Chandni Chowk", None, "market", 90, "Central Delhi", 5),
            ("Raj Ghat and associated memorials", "Raj Ghat", "monument", 30, "Central Delhi", 4),
            ("Purana Qila", None, "monument", 75, "New Delhi", 4),
            ("Lodhi Garden", "Lodhi Gardens", "nature", 60, "New Delhi", 4),
            ("Gurudwara Bangla Sahib", None, "temple", 45, "New Delhi", 4),
            ("National Museum, New Delhi", None, "museum", 120, "New Delhi", 4),
            ("Hauz Khas Complex", None, "monument", 60, "South Delhi", 3),
            ("Agrasen ki Baoli", None, "monument", 30, "New Delhi", 3),
            ("Safdarjung's Tomb", None, "monument", 45, "New Delhi", 3),
            ("Nizamuddin Dargah", None, "temple", 45, "South East Delhi", 3),
            ("Tughlaqabad Fort", None, "monument", 60, "South Delhi", 3),
            ("Jantar Mantar, New Delhi", "Jantar Mantar, New Delhi", "monument", 30, "New Delhi", 3),
            ("Mehrauli Archaeological Park", None, "monument", 90, "South Delhi", 3),
            ("Dilli Haat", None, "market", 90, "South Delhi", 3),
            ("National Rail Museum", None, "museum", 90, "New Delhi", 3),
        ],
    },
    "agra": {
        "city": "Agra",
        "city_pages": ["Agra"],
        "places": [
            ("Taj Mahal", None, "monument", 150, "Agra", 5),
            ("Agra Fort", None, "monument", 120, "Agra", 5),
            ("Fatehpur Sikri", None, "monument", 180, "Agra", 5),
            ("Tomb of I'timād-ud-Daulah", "Itimad-ud-Daulah's Tomb", "monument", 60, "Agra", 4),
            ("Mehtab Bagh", None, "viewpoint", 45, "Agra", 4),
            ("Akbar's tomb", "Akbar's Tomb, Sikandra", "monument", 60, "Agra", 4),
            ("Jama Masjid, Agra", None, "monument", 30, "Agra", 3),
            ("Chini Ka Rauza", None, "monument", 20, "Agra", 2),
            ("Ram Bagh", "Aram Bagh", "nature", 30, "Agra", 2),
            ("Buland Darwaza", None, "monument", 30, "Agra", 4),
            ("Panch Mahal", None, "monument", 20, "Agra", 3),
            ("Tomb of Salim Chishti", None, "monument", 30, "Agra", 4),
            ("Mariam-uz-Zamani's Tomb", "Tomb of Mariam-uz-Zamani", "monument", 30, "Agra", 2),
            ("Guru Ka Taal", None, "temple", 30, "Agra", 2),
            ("Dayal Bagh", "Dayalbagh", "temple", 45, "Agra", 2),
            ("Keetham Lake", "Sur Sarovar Bird Sanctuary (Keetham Lake)", "nature", 90, "Agra", 2),
            ("Jodha Bai Palace", None, "monument", 30, "Agra", 3),
            ("Hiran Minar", None, "monument", 20, "Agra", 2),
            ("Musamman Burj", None, "monument", 20, "Agra", 3),
            ("Diwan-i-Am (Agra)", "Diwan-i-Am, Agra Fort", "monument", 20, "Agra", 3),
            ("Jahangiri Mahal", None, "monument", 30, "Agra", 3),
            ("Khas Mahal (Agra)", "Khas Mahal, Agra Fort", "monument", 20, "Agra", 3),
            ("Moti Masjid (Agra)", "Moti Masjid, Agra Fort", "monument", 20, "Agra", 2),
            ("Sikandra, Agra", "Sikandra", "experience", 60, "Agra", 2),
        ],
    },
    "jaipur": {
        "city": "Jaipur",
        "city_pages": ["Jaipur"],
        "places": [
            ("Amer Fort", "Amber Fort", "monument", 150, "Jaipur", 5),
            ("Hawa Mahal", None, "monument", 45, "Jaipur", 5),
            ("City Palace, Jaipur", None, "museum", 120, "Jaipur", 5),
            ("Jantar Mantar, Jaipur", "Jantar Mantar, Jaipur", "monument", 60, "Jaipur", 4),
            ("Nahargarh Fort", None, "viewpoint", 90, "Jaipur", 4),
            ("Jaigarh Fort", None, "monument", 90, "Jaipur", 4),
            ("Jal Mahal", None, "viewpoint", 30, "Jaipur", 4),
            ("Albert Hall Museum", None, "museum", 75, "Jaipur", 4),
            ("Birla Mandir, Jaipur", None, "temple", 30, "Jaipur", 3),
            ("Galtaji", None, "temple", 60, "Jaipur", 3),
            ("Panna Meena ka Kund", None, "monument", 20, "Jaipur", 3),
            ("Sisodia Rani Garden", None, "nature", 45, "Jaipur", 2),
            ("Johari Bazaar", None, "market", 90, "Jaipur", 4),
            ("Govind Dev Ji Temple", None, "temple", 30, "Jaipur", 3),
            ("Chokhi Dhani", None, "experience", 180, "Jaipur", 3),
            ("Jawahar Kala Kendra", None, "museum", 60, "Jaipur", 2),
            ("Moti Dungri", "Moti Dungri Ganesh Temple", "temple", 30, "Jaipur", 3),
            ("Gaitore", None, "monument", 30, "Jaipur", 3),
            ("Anokhi Museum of Hand Printing", None, "museum", 45, "Jaipur", 2),
            ("Sanganer", "Sanganer (block printing)", "experience", 90, "Jaipur", 2),
            ("Raj Mandir Cinema", None, "experience", 180, "Jaipur", 3),
            ("Ram Niwas Garden", None, "nature", 45, "Jaipur", 2),
            ("Jhalana Safari Park", "Jhalana Leopard Reserve", "nature", 150, "Jaipur", 3),
        ],
    },
}


#: Official ticket sites only (HQ P8), each checked to answer on 28 Oct 2026: ASI's
#: e-ticket portal for its ticketed monuments, the Taj Mahal's own site, and Rajasthan's
#: online booking for the state's monuments. A place without one gets none.
#: Wikidata labels a traveller would not recognise: Qutub Minar's Hindi label is a fringe
#: name ("ध्रुव स्तम्भ"); the backwaters' is a coinage. The names people use instead.
NAME_FIX = {
    "Qutub Minar": {"hi": "क़ुतुब मीनार"},
    "Alleppey backwaters": {"hi": "अलप्पुझा के बैकवाटर्स"},
}
ASI_TICKETS = "https://asi.payumoney.com/"
TICKETS = {
    "Taj Mahal": "https://www.tajmahal.gov.in/",
    **dict.fromkeys([
        "Red Fort", "Qutub Minar", "Humayun's Tomb", "Purana Qila", "Safdarjung's Tomb", "Tughlaqabad Fort",
        "Jantar Mantar, New Delhi", "Agra Fort", "Fatehpur Sikri", "Itimad-ud-Daulah's Tomb",
        "Akbar's Tomb, Sikandra", "Mehtab Bagh", "Aram Bagh", "Mattancherry Palace (Dutch Palace)",
    ], ASI_TICKETS),
    **dict.fromkeys(["Amber Fort", "Hawa Mahal", "Jantar Mantar, Jaipur", "Nahargarh Fort", "Albert Hall Museum"],
                    "https://obms-tourist.rajasthan.gov.in/"),
}  # fmt: skip


def pick_coords(wikidata: tuple, wikipedia: tuple) -> tuple:
    """Wikidata's coordinates, unless Wikipedia's are far from them (or Wikidata has none)."""
    if wikidata[0] is None:
        return wikipedia
    if wikipedia[0] is not None and km(*wikidata, *wikipedia) > MAX_DISAGREE_KM:
        return wikipedia
    return wikidata


def in_bbox(region: str, lat: float, lng: float) -> bool:
    lat0, lat1, lng0, lng1 = BBOX[region]
    return lat0 <= lat <= lat1 and lng0 <= lng <= lng1


def build(region: str, wiki: WikiClient) -> tuple[list[dict], list[dict], list[str]]:
    spec = REGIONS[region]
    city, today = spec["city"], date.today().isoformat()
    pois, chunks, skipped, titles = [], [], [], set()

    def add_chunks(poi_name: str | None, page: str, cap: int = MAX_CHUNKS) -> int:
        url, sections = wiki.sections(page)
        time.sleep(PAUSE_S)
        n = 0
        for heading, body in sections:
            for i, para in enumerate(paragraphs(body)):
                if n >= cap:
                    return n
                n += 1
                label = page if heading == "Introduction" else f"{page}: {heading}"
                title = label if i == 0 else f"{label} ({i + 1})"
                while title in titles:  # a page with two "Architecture" sections
                    title += "'"
                titles.add(title)
                chunks.append({
                    "poi": poi_name, "city": city, "lang": "en",
                    "title": title,
                    "body": para, "chunk_type": "fact", "is_legend": False,
                    "source_name": "Wikipedia (CC BY-SA)", "source_url": url, "last_verified": today,
                })  # fmt: skip
        return n

    for title, display, category, minutes, district, popularity in spec["places"]:
        data = wiki.labels(title)
        time.sleep(PAUSE_S)
        s = wiki.summary(COORDS_PAGE.get(title, title))
        time.sleep(PAUSE_S)
        if not data["qid"] and (canonical := wiki.summary(title)["title"]) != title:
            # Wikidata matches the exact sitelink: "Humayun's Tomb" redirects to "Humayun's tomb".
            data = wiki.labels(canonical)
            time.sleep(PAUSE_S)
        lat, lng = pick_coords((data["lat"], data["lng"]), (s["lat"], s["lng"]))
        if lat is None or not data["qid"]:
            skipped.append(f"{title}: no Wikidata item or coordinates")
            continue
        if not in_bbox(region, lat, lng):
            skipped.append(f"{title}: coordinates {lat}, {lng} are outside {region}")
            continue
        name = display or data["labels"].get("en") or title
        names = {k: v for k, v in data["labels"].items() if k != "en"}
        names |= NAME_FIX.get(name, {})
        pois.append({
            "name": name, "name_kn": names.get("kn"), "names": names, "city": city,
            "district": district, "lat": round(lat, 5), "lng": round(lng, 5),
            "category": category, "tags": ["hours-unverified", "fee-unverified"],
            "typical_dwell_min": minutes, "opens": None, "closes": None, "closed_on": [],
            "popularity": popularity, "elderly_friendly": True, "trust": "draft",
            "source_url": f"https://www.wikidata.org/wiki/{data['qid']}", "last_verified": today,
            **({"ticket_url": TICKETS[name]} if name in TICKETS else {}),
        })  # fmt: skip
        if not add_chunks(name, title, MAX_CHUNKS_TOP if popularity >= 5 else MAX_CHUNKS):
            skipped.append(f"{title}: no prose paragraphs")
    for page in spec["city_pages"]:
        add_chunks(None, page, MAX_CHUNKS_TOP)
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
