import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import router
from routes.irctc import NotFound, irctc_card, pnr_status


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
    card = irctc_card("SBC", "MAO", dt.date(2026, 12, 11))
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


def test_fare_scales_with_class_and_party():
    d = dt.date(2026, 12, 11)
    sl, a3 = irctc_card("SBC", "MAO", d, "SL"), irctc_card("SBC", "MAO", d, "3A")
    assert a3.fare_estimate_inr > sl.fare_estimate_inr
    two = irctc_card("SBC", "MYS", d, "SL", "mysuru_weekend")
    four = irctc_card("SBC", "MYS", d, "SL", "goa_family")
    assert four.fare_estimate_inr == 2 * two.fare_estimate_inr


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


def test_pnr_timeline_replays_up_to_at():
    early = pnr_status("1234567890", dt.datetime(2026, 11, 1, tzinfo=IST))
    assert early.current_status == "WL 12" and len(early.timeline) == 1 and not early.chart_prepared
    assert {p.status for p in early.passengers} == {"WL 12"}
    done = pnr_status("1234567890", dt.datetime(2026, 12, 11, 20, tzinfo=IST))
    assert done.current_status == "CNF" and done.chart_prepared
    assert [p.status for p in done.passengers][:2] == ["CNF B2 34", "CNF B2 33"]
    assert done.train == "90001 Sample Bengaluru-Vasco Express" and done.from_.code == "SBC"


def test_pnr_before_booking_and_naive_at():
    s = pnr_status("4521690144", dt.datetime(2026, 10, 1))
    assert s.current_status == "NOT BOOKED YET" and s.timeline == []


def test_return_pnr_matches_prototype():
    s = pnr_status("4521690144", dt.datetime(2026, 10, 27, 12, tzinfo=IST))
    assert [e.status for e in s.timeline] == ["WL 19", "WL 15", "WL 12", "WL 7"]
    assert s.to.code == "SBC" and s.train.startswith("90010")


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
