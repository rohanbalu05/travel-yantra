#!/usr/bin/env python3
"""Record real API responses into fixtures/recorded/<provider>/ (card #16).

Live calls happen only here, from the record-fixtures workflow, with keys
read from GOOGLE_MAPS_API_KEY and SERPAPI_API_KEY. Tests never run this.

  python3 infra/fixtures/record.py --out fixtures/recorded           # everything
  python3 infra/fixtures/record.py --out /tmp/x --only wikimedia      # keyless part
  python3 infra/fixtures/record.py --out /tmp/x --plan                # list calls, no network

Personal data stays out by construction: Places field masks never ask for
phone numbers or reviews, and scrub() drops phone fields and api_key query
parameters before anything is written. sanitise.py then checks the result.
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

UA = "TravelYantraFixtures/1.0 (https://github.com/rohanbalu05/travel-yantra)"
DATE_IN, DATE_OUT = "2026-12-11", "2026-12-12"
SERPAPI_MAX = 10  # card #16: at most 10 SerpApi searches, free plan

PLACES = {
    "mysuru-palace": "Mysuru Palace, Mysuru, Karnataka",
    "bom-jesus": "Basilica of Bom Jesus, Old Goa",
    "hampi-virupaksha": "Virupaksha Temple, Hampi, Karnataka",
}
HOSPITALS = "hospital near Panaji, Goa"
PLACES_FIELDS = ",".join([
    "id", "displayName", "formattedAddress", "location", "types", "primaryType",
    "rating", "userRatingCount", "regularOpeningHours", "websiteUri",
    "googleMapsUri", "editorialSummary", "businessStatus",
])
SEARCH_FIELDS = ",".join("places." + f for f in PLACES_FIELDS.split(","))
ROUTE_FIELDS = "routes.duration,routes.staticDuration,routes.distanceMeters,routes.description,routes.localizedValues,routes.polyline.encodedPolyline"

WIKI_TITLES = {  # file name: (Wikipedia title, Wikivoyage title or None)
    "mysuru": ("Mysore", "Mysore"),
    "hampi": ("Hampi", "Hampi"),
    "goa": ("Goa", "Goa"),
    "mysuru-palace": ("Mysore_Palace", None),
    "bom-jesus": ("Basilica_of_Bom_Jesus", None),
    "hampi-virupaksha": ("Virupaksha_Temple,_Hampi", None),
}
LABEL_LANGS = "hi|kn|ta|te|bn|en"

FLIGHTS = {"blr-goi": ("BLR", "GOI"), "bom-goi": ("BOM", "GOI")}
HOTELS = {"panaji": "hotels in Panaji, Goa", "mysuru": "hotels in Mysuru, Karnataka"}

DROP_KEYS = {
    "nationalPhoneNumber", "internationalPhoneNumber", "phone", "phone_number",
    "phone_numbers", "telephone", "tel", "contact", "contact_phone",
    "reviews", "authorAttribution", "author", "user", "profile_photo_url",
}
KEY_PARAM = re.compile(r"([?&])(api_key|key)=[^&\"\s]*")


def scrub(obj):
    """Drop personal-data fields and strip key parameters from URL strings."""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items() if k not in DROP_KEYS}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    if isinstance(obj, str):
        return KEY_PARAM.sub(r"\1\2=REDACTED", obj)
    return obj


def http(url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


class Recorder:
    def __init__(self, out, plan=False):
        self.out, self.plan, self.calls, self.serpapi = Path(out), plan, [], 0

    def call(self, provider, url, body=None, headers=None):
        self.calls.append((provider, KEY_PARAM.sub(r"\1\2=REDACTED", url)))
        if provider == "serpapi":
            self.serpapi += 1
            if self.serpapi > SERPAPI_MAX:
                raise SystemExit(f"SerpApi budget exceeded ({SERPAPI_MAX})")
        return {} if self.plan else http(url, body, headers)

    def save(self, provider, name, data):
        if self.plan:
            return
        p = self.out / provider / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(scrub(data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {p}")


def maps_headers(fields):
    return {"X-Goog-Api-Key": os.environ.get("GOOGLE_MAPS_API_KEY", ""), "X-Goog-FieldMask": fields}


def record_places(rec):
    url = "https://places.googleapis.com/v1/places:searchText"
    for name, query in PLACES.items():
        found = rec.call("places", url, {"textQuery": query, "maxResultCount": 1, "languageCode": "en", "regionCode": "IN"}, maps_headers(SEARCH_FIELDS))
        rec.save("places", f"search-{name}", found)
        pid = (found.get("places") or [{}])[0].get("id", "PLACE_ID")
        rec.save("places", f"details-{name}", rec.call("places", f"https://places.googleapis.com/v1/places/{pid}", None, maps_headers(PLACES_FIELDS)))
    found = rec.call("places", url, {"textQuery": HOSPITALS, "maxResultCount": 2, "languageCode": "en", "regionCode": "IN"}, maps_headers(SEARCH_FIELDS))
    rec.save("places", "search-hospitals-panaji", found)
    for i, place in enumerate((found.get("places") or [{}, {}])[:2], 1):
        pid = place.get("id", "PLACE_ID")
        rec.save("places", f"details-hospital-panaji-{i}", rec.call("places", f"https://places.googleapis.com/v1/places/{pid}", None, maps_headers(PLACES_FIELDS)))


def record_routes(rec):
    body = {"origin": {"address": "Bengaluru, Karnataka"}, "destination": {"address": "Panaji, Goa"},
            "travelMode": "DRIVE", "languageCode": "en-IN", "units": "METRIC"}
    rec.save("routes", "drive-bengaluru-panaji", rec.call("routes", "https://routes.googleapis.com/directions/v2:computeRoutes", body, maps_headers(ROUTE_FIELDS)))


def record_wikimedia(rec):
    for name, (wp, wv) in WIKI_TITLES.items():
        summary = rec.call("wikimedia", f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(wp)}")
        rec.save("wikimedia", f"wikipedia-{name}", summary)
        if wv:
            rec.save("wikimedia", f"wikivoyage-{name}", rec.call("wikimedia", f"https://en.wikivoyage.org/api/rest_v1/page/summary/{urllib.parse.quote(wv)}"))
        qid = summary.get("wikibase_item", "Q0")
        q = urllib.parse.urlencode({"action": "wbgetentities", "ids": qid, "props": "labels", "languages": LABEL_LANGS, "format": "json"})
        rec.save("wikimedia", f"wikidata-labels-{name}", rec.call("wikimedia", f"https://www.wikidata.org/w/api.php?{q}"))


def serp(rec, **params):
    params.update(api_key=os.environ.get("SERPAPI_API_KEY", ""), hl="en", gl="in", currency="INR")
    return rec.call("serpapi", "https://serpapi.com/search.json?" + urllib.parse.urlencode(params))


def record_serpapi(rec):
    sellers = {}
    for name, (dep, arr) in FLIGHTS.items():
        base = dict(engine="google_flights", departure_id=dep, arrival_id=arr, outbound_date=DATE_IN, type="2")
        found = serp(rec, **base)
        rec.save("serpapi", f"flights-{name}", found)
        flights = (found.get("best_flights") or []) + (found.get("other_flights") or [])
        token = next((f.get("booking_token") for f in flights if f.get("booking_token")), "TOKEN")
        booking = serp(rec, **base, booking_token=token)
        rec.save("serpapi", f"flights-{name}-booking", booking)
        sellers[f"flights-{name}"] = sorted({o.get("together", {}).get("book_with", "?") for o in booking.get("booking_options", [])})
    for name, q in HOTELS.items():
        base = dict(engine="google_hotels", q=q, check_in_date=DATE_IN, check_out_date=DATE_OUT, adults="2")
        found = serp(rec, **base)
        rec.save("serpapi", f"hotels-{name}", found)
        token = next((p.get("property_token") for p in found.get("properties", []) if p.get("property_token")), "TOKEN")
        details = serp(rec, **base, property_token=token)
        rec.save("serpapi", f"hotels-{name}-property", details)
        sellers[f"hotels-{name}"] = sorted({p.get("source", "?") for p in details.get("prices", [])})
    rec.save("serpapi", "sellers-summary", sellers)
    if not rec.plan:
        print("sellers:", json.dumps(sellers, ensure_ascii=False))


PROVIDERS = {"places": record_places, "routes": record_routes, "wikimedia": record_wikimedia, "serpapi": record_serpapi}
NEEDS_KEY = {"places": "GOOGLE_MAPS_API_KEY", "routes": "GOOGLE_MAPS_API_KEY", "serpapi": "SERPAPI_API_KEY"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", choices=sorted(PROVIDERS), action="append")
    ap.add_argument("--plan", action="store_true", help="list the calls without making them")
    args = ap.parse_args(argv)
    rec = Recorder(args.out, plan=args.plan)
    for name in args.only or list(PROVIDERS):
        key = NEEDS_KEY.get(name)
        if key and not args.plan and not os.environ.get(key):
            print(f"skip {name}: {key} is not set")
            continue
        PROVIDERS[name](rec)
    for provider, url in rec.calls:
        print(f"{'planned' if args.plan else 'called'} {provider} {url}")
    print(f"calls: {len(rec.calls)} (serpapi {rec.serpapi}/{SERPAPI_MAX})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
