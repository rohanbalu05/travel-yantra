"""Live smoke for P2 and fixture recorder: a few compares and stays through the
real SerpApi and Routes API code paths, then sanitised, trimmed fixtures for
the tests. Never run by tests. Every live call goes through the shared cache
and the counters, so a rerun with a warm cache makes no calls.

    cd apps/api && uv run python -m routes.scripts.record_live [--no-road]

Needs SERPAPI_API_KEY and GOOGLE_MAPS_API_KEY (names only; values are never
printed). The Routes API gets one live call (Bengaluru -> Goa); every other
road edge is haversine or cache."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

from routes import apicache
from routes.compare import CompareService
from routes.flights import SerpApiFlights
from routes.hotels import SerpApiHotels
from routes.roads import RoutesApiRoadProvider
from routes.serpapi import SerpApi, sanitise
from routes.stays import rank_stays
from ty_contracts import CompareRequest

OUT = Path(__file__).resolve().parents[2] / "tests" / "routes" / "fixtures"
DAY = dt.date(2026, 12, 11)
NIGHTS = 3
PARTY = 4  # the sample Rao family
NOTE = ("Recorded live from SerpApi on {date} by routes/scripts/record_live.py; sanitised "
        "(request metadata, phone fields, images dropped) and trimmed.")

FLIGHT_KEEP = ("flights", "layovers", "total_duration", "price", "type", "booking_token")
SEG_KEEP = ("departure_airport", "arrival_airport", "duration", "airline", "flight_number", "travel_class")
PROP_KEEP = ("type", "name", "rate_per_night", "total_rate", "overall_rating", "reviews", "hotel_class",
             "property_token", "gps_coordinates", "prices")
PRICE_KEEP = ("source", "link", "official", "num_guests", "rate_per_night", "total_rate")


def _pick(d: dict, keys) -> dict:
    return {k: d[k] for k in keys if k in d}


def trim(params: dict, payload: dict) -> dict:
    if params["engine"] == "google_flights" and "booking_token" in params:
        opts = [{"together": _pick(o.get("together") or {}, ("book_with", "airline", "marketed_as",
                                                              "price", "option_title"))}
                for o in payload.get("booking_options") or []]
        return {"booking_options": opts}
    if params["engine"] == "google_flights":
        def group(g):
            g = _pick(g, FLIGHT_KEEP)
            g["flights"] = [_pick(s, SEG_KEEP) for s in g.get("flights") or []]
            return g
        return {"best_flights": [group(g) for g in payload.get("best_flights") or []],
                "other_flights": [group(g) for g in payload.get("other_flights") or []]}
    if "property_token" in params:
        out = _pick(payload, ("type", "name", "rate_per_night", "total_rate", "overall_rating"))
        for k in ("featured_prices", "prices"):
            out[k] = [_pick(p, PRICE_KEEP) for p in payload.get(k) or []]
        return out
    props = []
    for p in payload.get("properties") or []:
        p = _pick(p, PROP_KEEP)
        if "prices" in p:
            p["prices"] = [_pick(x, PRICE_KEEP) for x in p["prices"]]
        props.append(p)
    return {"properties": props}


def _name(params: dict) -> str:
    if params["engine"] == "google_flights":
        base = f"flights_{params['departure_id']}_{params['arrival_id']}".lower()
        return base + ("_booking" if "booking_token" in params else "")
    city = params["q"].removeprefix("hotels in ").lower().replace(" ", "_")
    return f"hotels_{city}" + ("_details" if "property_token" in params else "")


def main() -> None:
    store = apicache.get_store()
    api = SerpApi(store=store)
    seen: dict[str, tuple[dict, dict]] = {}
    plain_get = api.get

    def get(params, ttl_s):
        payload = plain_get(params, ttl_s)
        if payload is not None:
            seen[_name(params)] = (params, payload)
        return payload

    api.get = get
    road_calls: list[dict] = []
    road = RoutesApiRoadProvider(cache=store, max_live_calls=0 if "--no-road" in sys.argv else 1)
    plain_transport = road._transport

    def transport(url, headers, body, timeout):
        payload = plain_transport(url, headers, body, timeout)
        road_calls.append({"body": body, "payload": payload})
        return payload

    road._transport = transport

    svc = CompareService(road=road, flights=SerpApiFlights(api))
    for dest in ("Goa", "Mysuru", "Hampi", "Coorg", "Chikmagalur"):
        r = svc.compare(CompareRequest(origin="Bengaluru", destination=dest, date=DAY, travellers=PARTY))
        print(f"compare Bengaluru -> {dest}:")
        for o in r.options:
            print(f"  {o.rank}. {o.option.mode:<4} {o.option.total_minutes:>5} min  Rs {o.option.total_cost_inr:>6}"
                  f"  changes {o.changes}  {','.join(o.sources)}  offers {len(o.option.offers)}"
                  f" (priced {sum(x.price_inr is not None for x in o.option.offers)})")
        for u in r.unavailable:
            print(f"  -  {u.mode:<4} {u.reason}")

    hotels = SerpApiHotels(api)
    for city in ("Goa", "Coorg", "Hampi", "Chikmagalur"):
        stays = rank_stays(city, DAY, DAY + dt.timedelta(days=NIGHTS), party=PARTY, hotels=hotels)
        print(f"stays {city}:")
        for s in stays:
            priced = [o for o in s.offers if o.price_inr is not None]
            print(f"  {s.name[:40]:<40} Rs {s.price_per_night_inr:>6}/night  offers {len(s.offers)} (priced {len(priced)})")

    today = date_str = dt.date.today().isoformat()
    print(f"serpapi live calls this run: {api.live_calls}; today (shared counter): "
          f"{store.count('serpapi', apicache.day_period())}; this month: {store.count('serpapi', apicache.month_period())}")
    print(f"routes api live calls this run: {road.live_calls}; this month: {store.count('routes_api', apicache.month_period())}")

    key = os.environ.get("SERPAPI_API_KEY")
    (OUT / "serpapi").mkdir(parents=True, exist_ok=True)
    for name, (params, payload) in sorted(seen.items()):
        body = {"_note": NOTE.format(date=today), "_params": sanitise(params, key), **trim(params, payload)}
        text = json.dumps(sanitise(body, key), indent=1, ensure_ascii=False) + "\n"
        assert not key or key not in text
        (OUT / "serpapi" / f"{name}.json").write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote fixtures/serpapi/{name}.json")
    blr_goa = [c for c in road_calls if c["body"]["destination"]["location"]["latLng"]["latitude"] == 15.4909
               and c["body"]["origin"]["location"]["latLng"]["latitude"] == 12.9716]
    if blr_goa:
        call = blr_goa[0]
        body = {"_note": f"Recorded live from the Routes API on {date_str} (field mask routes.duration,"
                         "routes.distanceMeters), Bengaluru -> Panaji city centres.",
                "_request": call["body"], **call["payload"]}
        (OUT / "routes_api_blr_goa.json").write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8", newline="\n")
        print("wrote fixtures/routes_api_blr_goa.json")


if __name__ == "__main__":
    main()
