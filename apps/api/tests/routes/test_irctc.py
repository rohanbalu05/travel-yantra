import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import router
from routes.fares import rail_fare
from routes.graph import DATA_DIR, RAIL_DETOUR, haversine_km
from routes.irctc import NotFound, irctc_card, pnr_status, resolve_station


@pytest.fixture(autouse=True)
def sample_rail(monkeypatch):
    """These tests cover the logic on the small fictional sample network."""
    monkeypatch.setenv("ROUTES_RAIL", "sample")


IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_goa_card_has_irctc_form_fields_in_order():
    card = irctc_card("SBC", "MAO", dt.date(2026, 12, 11), after=dt.time(23, 0))
    assert card.train.number == "90001" and card.travel_class == "3A" and card.quota == "General"
    assert (card.departs, card.arrives, card.arrives_day_offset) == ("23:30", "10:40", 1)
    assert card.date_irctc == "11-12-2026" and card.sample
    assert [p.name for p in card.passengers] == ["Arjun Rao", "Venkatesh", "Shobha", "Meera"]
    assert [p.berth for p in card.passengers] == ["Upper", "Lower", "Lower", "Middle"]
    lines = card.copy_text.splitlines()
    assert [ln.split(":")[0] for ln in lines[:6]] == ["From", "To", "Date", "Class", "Quota", "Train"]
    assert lines[-1] == "4. Meera, 22, Female, Middle"
    assert card.fare_estimate_inr > 0 and card.booking_url.startswith("https://www.irctc.co.in/")


def test_card_accepts_compare_leg_station_names_and_party():
    card = irctc_card("KSR Bengaluru City Jn", "mysuru jn", dt.date(2026, 10, 31), "CC", "mysuru_weekend")
    assert card.train.number == "90008" and len(card.passengers) == 2
    assert {p.berth for p in card.passengers} == {"No preference"}


def test_without_a_train_the_card_takes_the_first_leaving_after():
    d = dt.date(2026, 12, 11)
    default, late = irctc_card("SBC", "MAO", d), irctc_card("SBC", "MAO", d, after=dt.time(23, 0))
    assert default.departs >= "06:00" and late.departs == "23:30" and default.train.number != late.train.number


def test_class_must_be_one_the_train_carries():
    """Real datameet trains: the Mysuru Shatabdi has CC and EC only, so 3A becomes CC (QA: the card
    offered 3A on 12007); with no class the mid style's class; the fare is compare's rail fare."""
    d = dt.date(2026, 12, 11)
    card = irctc_card("SBC", "MYS", d, "3A", "mysuru_weekend", train="12007", data_dir=DATA_DIR)
    assert card.train.number == "12007" and card.classes == ["CC", "EC"] and card.travel_class == "CC"
    assert any("no 3A" in n for n in card.notes)
    assert irctc_card("SBC", "MYS", d, None, "mysuru_weekend", "12007", DATA_DIR, style="luxury").travel_class == "EC"
    express = irctc_card("SBC", "MYS", d, None, "mysuru_weekend", "16731", DATA_DIR)
    assert express.travel_class == "3A" and "3A" in express.classes and not any("no " in n for n in express.notes)
    assert card.fare_estimate_inr == 2 * rail_fare(
        haversine_km(*_ll("SBC"), *_ll("MYS")) * RAIL_DETOUR, "CC")


def _ll(code: str) -> tuple[float, float]:
    s = resolve_station(code, DATA_DIR)
    return s["lat"], s["lon"]


def test_fare_scales_with_class_and_party():
    d = dt.date(2026, 12, 11)
    sl, a3 = irctc_card("SBC", "MAO", d, "SL"), irctc_card("SBC", "MAO", d, "3A")
    assert a3.fare_estimate_inr > sl.fare_estimate_inr
    two = irctc_card("SBC", "MYS", d, "SL", "mysuru_weekend")
    four = irctc_card("SBC", "MYS", d, "SL", "goa_family")
    assert four.fare_estimate_inr == 2 * two.fare_estimate_inr


def test_passengers_match_the_trip_party_size():
    d = dt.date(2026, 10, 31)
    three = irctc_card("SBC", "MYS", d, "CC", "mysuru_weekend", travellers=3)
    assert [p.name for p in three.passengers] == ["Arjun Rao", "Meera", "Venkatesh"]
    assert three.fare_estimate_inr == 3 * irctc_card("SBC", "MYS", d, "CC", travellers=1).fare_estimate_inr
    six = irctc_card("SBC", "MYS", d, "SL", "goa_family", travellers=6)
    assert len(six.passengers) == 6 and six.passengers[-1].name == "Traveller 6"
    assert [p.name for p in irctc_card("SBC", "MYS", d, travellers=1).passengers] == ["Arjun Rao"]


@pytest.mark.parametrize("src,dst,train", [("MAO", "MYS", None), ("SBC", "MAO", "90004"), ("XXX", "MAO", None)])
def test_card_not_found(src, dst, train):
    with pytest.raises(NotFound):
        irctc_card(src, dst, dt.date(2026, 12, 11), train=train)


def test_http_irctc_card(client):
    res = client.get("/routes/irctc-card", params={"from": "KSR Bengaluru City Jn", "to": "Madgaon Jn",
                                                   "date": "2026-12-11", "train": "90002"})
    assert res.status_code == 200
    body = res.json()
    assert body["from"]["code"] == "SBC" and body["train"]["number"] == "90002"
    assert client.get("/routes/irctc-card", params={"from": "MAO", "to": "MYS",
                                                    "date": "2026-12-11"}).status_code == 404
    assert client.get("/routes/irctc-card", params={"from": "SBC", "to": "MAO", "date": "2026-12-11",
                                                    "travel_class": "XL"}).status_code == 422
    three = client.get("/routes/irctc-card", params={"from": "SBC", "to": "MAO", "date": "2026-12-11", "travellers": 3})
    assert len(three.json()["passengers"]) == 3
    assert client.get("/routes/irctc-card", params={"from": "SBC", "to": "MAO", "date": "2026-12-11",
                                                    "travellers": 7}).status_code == 422


def test_pnr_timeline_replays_up_to_at():
    early = pnr_status("1234567890", dt.datetime(2026, 11, 1, tzinfo=IST))
    assert early.current_status == "WL 12" and len(early.timeline) == 1 and not early.chart_prepared
    assert {p.status for p in early.passengers} == {"WL 12"}
    done = pnr_status("1234567890", dt.datetime(2026, 12, 11, 20, tzinfo=IST))
    assert done.current_status == "CNF" and done.chart_prepared
    assert [p.status for p in done.passengers][:2] == ["CNF B2 34", "CNF B2 33"]
    assert done.train == "17309 Yesvantpur - Vasco DA Gama Exp" and done.from_.code == "YPR"
    assert done.from_.name == "Yesvantpur JN" and done.to.code == "VSG"


def test_pnr_before_booking_and_naive_at():
    s = pnr_status("4521690144", dt.datetime(2026, 10, 1))
    assert s.current_status == "NOT BOOKED YET" and s.timeline == []


def test_return_pnr_matches_prototype():
    s = pnr_status("4521690144", dt.datetime(2026, 10, 27, 12, tzinfo=IST))
    assert [e.status for e in s.timeline] == ["WL 19", "WL 15", "WL 12", "WL 7"]
    assert s.to.code == "YPR" and s.train.startswith("17310 ")


def test_http_pnr_mock(client):
    res = client.get("/routes/pnr-mock", params={"pnr": "1234567890", "at": "2026-12-12T00:00:00+05:30"})
    assert res.status_code == 200
    body = res.json()
    assert {"pnr", "train", "class", "date", "from", "to", "passengers", "timeline", "current_status",
            "chart_prepared", "sample"} <= set(body)
    assert body["sample"] is True and body["class"] == "3A"
    missing = client.get("/routes/pnr-mock", params={"pnr": "9999999999"})
    assert missing.status_code == 404 and missing.json()["detail"] == "unknown sample PNR"
    assert client.get("/routes/pnr-mock", params={"pnr": "12345"}).status_code == 422


def test_card_on_the_real_timetable_from_compare_station_names(monkeypatch):
    monkeypatch.delenv("ROUTES_RAIL")
    card = irctc_card("Yesvantpur JN", "Dabolim", dt.date(2026, 12, 11))
    assert card.train.number == "17309" and card.departs == "15:15" and card.from_.code == "YPR"
    assert "datameet" in card.notes[0]


@pytest.mark.parametrize("src,dst,train,stations,departs", [
    ("Bengaluru", "Mysuru", "16731", ("SBC", "MYS"), "07:00"),  # not Bangalore Cant at 05:43
    ("Mysuru", "Bengaluru", "16232", ("MYS", "BNC"), "15:45"),  # not Naganahalli further on
    ("Bengaluru", "Goa", "17309", ("YPR", "VSG"), "15:15"),
])
def test_card_from_a_plans_city_names_and_train(monkeypatch, src, dst, train, stations, departs):
    # a plan's journey leg names cities; with its train number the card finds the stations compare uses
    monkeypatch.delenv("ROUTES_RAIL")
    card = irctc_card(src, dst, dt.date(2026, 10, 31), "SL", "mysuru_weekend", train, travellers=3)
    assert (card.from_.code, card.to.code, card.departs) == (*stations, departs)
    assert card.train.number == train and len(card.passengers) == 3
    with pytest.raises(NotFound):  # a city name needs the train
        irctc_card(src, dst, dt.date(2026, 10, 31))


def test_every_sample_pnr_names_a_real_train_that_runs_between_its_stations(monkeypatch):
    monkeypatch.delenv("ROUTES_RAIL")
    from routes.irctc import _find_run, _pnrs

    for row in _pnrs().values():
        t, dep, arr = _find_run(row["from"], row["to"], row["train"], None)
        assert not t["number"].startswith("900") and dep["code"] == row["from"] and arr["code"] == row["to"]


def test_real_trip_gets_passenger_rows_with_its_ages_not_sample_names(client):
    res = client.get("/routes/irctc-card", params={"from": "SBC", "to": "MAO", "date": "2026-12-11",
                                                   "party": "none", "ages": "34,64,58,9"})
    assert res.status_code == 200
    body = res.json()
    assert [p["name"] for p in body["passengers"]] == ["Passenger 1", "Passenger 2", "Passenger 3", "Passenger 4"]
    assert [p["age"] for p in body["passengers"]] == [34, 64, 58, 9] and body["sample"] is False
    assert [p["berth"] for p in body["passengers"]][1:3] == ["Lower", "Lower"]
    assert "Arjun" not in body["copy_text"] and "2. Passenger 2, 64, Lower" in body["copy_text"]
    three = irctc_card("SBC", "MAO", dt.date(2026, 12, 11), party="none", travellers=3)
    assert len(three.passengers) == 3 and three.fare_estimate_inr == 3 * irctc_card(
        "SBC", "MAO", dt.date(2026, 12, 11), party="none", travellers=1).fare_estimate_inr
    assert client.get("/routes/irctc-card", params={"from": "SBC", "to": "MAO", "date": "2026-12-11",
                                                    "party": "none", "ages": "34;64"}).status_code == 422


def test_slip_portion_books_as_its_train():
    """Hyderabad to Hampi rides 17603-Slip2 in datameet: the leg and the card both say 17603."""
    from routes.compare import CompareService
    from routes.graph import HaversineRoadProvider

    svc = CompareService(road=HaversineRoadProvider(), data_dir=DATA_DIR, live=False)
    opts = svc.rail_departures("Hyderabad", "Hampi", dt.date(2026, 11, 21), travellers=2)
    legs = [leg for o in opts for leg in o.legs if leg.mode.value == "rail"]
    assert legs and all(leg.ref and leg.ref.isdigit() and len(leg.ref) == 5 for leg in legs)
    slip = next((leg for leg in legs if leg.ref == "17603"), None)
    assert slip is not None  # 17603-Slip2 in the datameet subset
    if slip is not None:
        card = irctc_card(slip.from_, slip.to, dt.date(2026, 11, 21), party="none", train="17603", data_dir=DATA_DIR,
                          travellers=2, after=slip.depart.time())
        assert card.train.number == "17603" and card.departs == slip.depart.strftime("%H:%M")
        assert card.fare_estimate_inr == slip.cost_inr
