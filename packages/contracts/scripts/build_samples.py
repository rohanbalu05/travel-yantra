"""Builds samples/*.json from typed models (sample data only; fares and PNRs are fake)."""

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from ty_contracts import (
    BudgetSummary,
    Constraints,
    DayPlan,
    Itinerary,
    Lang,
    Leg,
    Mode,
    OpeningHours,
    Pace,
    Place,
    SellerOffer,
    Stay,
    TransportOption,
    Traveller,
    TripRequest,
)

OUT = Path(__file__).resolve().parent.parent / "samples"
FETCHED = datetime(2026, 10, 20, 9, 0)
ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def hours(opens: int, closes: int) -> list[OpeningHours]:
    return [OpeningHours(day=d, opens=time(opens), closes=time(closes)) for d in ALL_DAYS]


def place(pid, name, lat, lng, cat, mins, o=9, c=18, native=None):
    return Place(id=pid, name=name, native_names=native or {}, lat=lat, lng=lng, category=cat,
                 opening_hours=hours(o, c), typical_visit_minutes=mins, source="sample")


def leg(a, b, mode, d, minutes, cost):
    return Leg(**{"from": a, "to": b}, mode=mode, depart=d, arrive=d + timedelta(minutes=minutes),
               minutes=minutes, cost_inr=cost)


def offer(seller, price, kind="deep_link"):
    return SellerOffer(seller=seller, price_inr=price, url=f"https://example.com/{seller.lower()}",
                       kind=kind, fetched_at=FETCHED)


def write(name, req, itin):
    data = {"request": req.model_dump(mode="json"), "itinerary": itin.model_dump(mode="json", by_alias=True)}
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def goa():
    req = TripRequest(
        origin="Bengaluru", destinations=["Goa"], start_date=date(2026, 12, 11), end_date=date(2026, 12, 14),
        lang=Lang.en, notes="Sample persona: Arjun Rao and family.",
        constraints=Constraints(
            budget_inr=60000, pace=Pace.relaxed, mobility_needs=["avoid long walks", "step-free access"],
            dietary=["vegetarian"], max_travel_hours_per_day=4,
            travellers=[Traveller(name="Arjun Rao", age=34), Traveller(name="Venkatesh", age=64),
                        Traveller(name="Shobha", age=58), Traveller(name="Meera", age=22)]))
    d0 = datetime(2026, 12, 11, 21, 0)
    rail = TransportOption(mode=Mode.rail, comfort=4, total_minutes=840, total_cost_inr=4800,
        legs=[leg("Bengaluru", "Madgaon", Mode.rail, d0, 840, 4800)],
        offers=[offer("IRCTC", 4800), offer("SampleTrain", 4950, "check_price")])
    air = TransportOption(mode=Mode.air, comfort=5, total_minutes=75, total_cost_inr=16400,
        legs=[leg("Bengaluru", "Goa (Dabolim)", Mode.air, datetime(2026, 12, 11, 8, 0), 75, 16400)],
        offers=[offer("SampleAir", 16400)])
    stops = [
        [place("goa-basilica", "Basilica of Bom Jesus", 15.5009, 73.9116, "heritage", 60, native={Lang.hi: "बॉम जीसस बेसिलिका"}),
         place("goa-sechurch", "Se Cathedral", 15.5025, 73.9115, "heritage", 45)],
        [place("goa-fontainhas", "Fontainhas Latin Quarter", 15.4963, 73.8312, "neighbourhood", 90),
         place("goa-miramar", "Miramar Beach sunset", 15.4822, 73.8109, "beach", 75, 0, 23)],
        [place("goa-mangeshi", "Shri Mangueshi Temple", 15.4468, 73.9726, "temple", 60, 6, 20,
               {Lang.hi: "श्री मंगेशी मंदिर", Lang.kn: "ಶ್ರೀ ಮಂಗೇಶಿ ದೇವಸ್ಥಾನ"})],
        [],
    ]
    notes = [["Arrive by morning train; rest at the hotel."], ["Short hops by cab only."], ["Temple first, then a slow lunch."],
             ["Check out at 11:00; evening train back."]]
    days = [DayPlan(date=date(2026, 12, 11) + timedelta(days=i), stops=stops[i], notes=notes[i],
                    legs=[leg(stops[i][0].name, stops[i][1].name, Mode.road, datetime(2026, 12, 11 + i, 15, 0), 20, 250)]
                    if len(stops[i]) > 1 else []) for i in range(4)]
    stay = Stay(name="Sample Heritage Inn", city="Panaji", check_in=date(2026, 12, 11), check_out=date(2026, 12, 14),
                price_per_night_inr=4200, offers=[offer("SampleStays", 4200)])
    itin = Itinerary(request=req, days=days, transport=[rail, air], stays=[stay], lang=Lang.en,
        budget=BudgetSummary(transport_inr=19200, stay_inr=12600, activities_inr=3000, food_inr=12000,
                             total_inr=46800, within_budget=True),
        warnings=["Rail fare is a sample (PNR 0000000000)."])
    write("goa_family.json", req, itin)


def mysuru():
    req = TripRequest(
        origin="Bengaluru", destinations=["Mysuru"], start_date=date(2026, 10, 31), end_date=date(2026, 11, 1),
        lang=Lang.en,
        constraints=Constraints(budget_inr=15000, pace=Pace.balanced, dietary=["vegetarian"], max_travel_hours_per_day=5,
                                travellers=[Traveller(name="Arjun Rao", age=34), Traveller(name="Meera", age=22)]))
    road = TransportOption(mode=Mode.road, comfort=3, total_minutes=190, total_cost_inr=1800,
        legs=[leg("Bengaluru", "Mysuru", Mode.road, datetime(2026, 10, 31, 7, 0), 190, 1800)],
        offers=[offer("SampleCabs", 1800, "check_price")])
    stops = [
        [place("mys-palace", "Mysore Palace", 12.3052, 76.6552, "heritage", 120, 10, 17, {Lang.kn: "ಮೈಸೂರು ಅರಮನೆ"}),
         place("mys-chamundi", "Chamundi Hill", 12.2724, 76.6701, "temple", 90, 7, 20)],
        [place("mys-devaraja", "Devaraja Market", 12.3079, 76.6532, "market", 60, 8, 20)],
    ]
    days = [DayPlan(date=date(2026, 10, 31), stops=stops[0], notes=["Palace before noon crowds."],
                    legs=[leg("Mysore Palace", "Chamundi Hill", Mode.road, datetime(2026, 10, 31, 14, 0), 25, 200)]),
            DayPlan(date=date(2026, 11, 1), stops=stops[1], notes=["Return to Bengaluru by evening."])]
    stay = Stay(name="Sample Palace View", city="Mysuru", check_in=date(2026, 10, 31), check_out=date(2026, 11, 1),
                price_per_night_inr=3200)
    itin = Itinerary(request=req, days=days, transport=[road], stays=[stay], lang=Lang.en,
        budget=BudgetSummary(transport_inr=3600, stay_inr=3200, activities_inr=600, food_inr=2400, total_inr=9800,
                             within_budget=True))
    write("mysuru_weekend.json", req, itin)


if __name__ == "__main__":
    goa()
    mysuru()
