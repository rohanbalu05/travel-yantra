import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from ty_contracts import (
    CompareRequest,
    CompareResponse,
    GuideAnswer,
    GuideQuestion,
    Itinerary,
    KathaRequest,
    KathaStory,
    Lang,
    PlanEvent,
    PlanStage,
    PlanText,
    ReviseRequest,
    TripRequest,
)

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = sorted((ROOT / "samples").glob("*.json"))


def roundtrip(model, obj):
    first = model.model_validate(obj)
    dumped = first.model_dump(mode="json", by_alias=True)
    assert model.model_validate(dumped) == first
    return first


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.stem)
def test_sample_validates_and_roundtrips(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    req = roundtrip(TripRequest, data["request"])
    itin = roundtrip(Itinerary, data["itinerary"])
    assert itin.request == req
    assert itin.days and itin.transport and itin.stays


def test_goa_sample_persona():
    data = json.loads((ROOT / "samples" / "goa_family.json").read_text(encoding="utf-8"))
    req = TripRequest.model_validate(data["request"])
    assert [t.age for t in req.constraints.travellers] == [34, 64, 58, 22]
    assert req.constraints.pace == "relaxed"
    assert (str(req.start_date), str(req.end_date)) == ("2026-12-11", "2026-12-14")


def test_mysuru_dates():
    data = json.loads((ROOT / "samples" / "mysuru_weekend.json").read_text(encoding="utf-8"))
    req = TripRequest.model_validate(data["request"])
    assert (str(req.start_date), str(req.end_date)) == ("2026-10-31", "2026-11-01")


def test_plan_event_roundtrip_with_and_without_partial():
    data = json.loads(SAMPLES[0].read_text(encoding="utf-8"))
    roundtrip(PlanEvent, {"stage": "planning", "message": "x", "partial": data["itinerary"]})
    ev = roundtrip(PlanEvent, {"stage": "intake", "message": "hi"})
    assert ev.partial is None
    assert [s.value for s in PlanStage] == [
        "intake", "planning", "solving", "checking", "repairing", "narrating", "needs_input", "done", "error"]


def test_plan_event_extra_fields_roundtrip_and_stay_optional():
    ev = roundtrip(PlanEvent, {
        "stage": "checking", "message": "2 issues", "step": "checker", "iteration": 1,
        "violations": [{"code": "closed", "message": "m", "day": "2026-12-12", "place_id": "goa-miramar"}]})
    assert ev.violations[0].code == "closed" and ev.iteration == 1
    ask = roundtrip(PlanEvent, {"stage": "needs_input", "message": "?", "questions": ["When?", "Who?"]})
    assert ask.questions == ["When?", "Who?"] and ask.retryable is False
    with pytest.raises(ValidationError):
        PlanEvent.model_validate({"stage": "needs_input", "message": "?", "questions": ["a", "b", "c", "d"]})
    with pytest.raises(ValidationError):
        PlanEvent.model_validate({"stage": "checking", "message": "x", "iteration": 4})
    assert roundtrip(PlanEvent, {"stage": "done", "message": "Done", "plan_id": "abc"}).plan_id == "abc"
    assert roundtrip(GuideQuestion, {"question": "Is it open?", "place_name": "Mysore Palace", "lat": 12.3}).lang == "en"
    resp = roundtrip(CompareResponse, {
        "origin": {"name": "Bengaluru", "lat": 12.97, "lng": 77.59}, "destination": {"name": "Goa", "lat": 15.5, "lng": 73.8},
        "date": "2026-12-11", "rank_by": "cost",
        "options": [{"id": "r1", "rank": 1, "changes": 0, "score": 1.0, "sources": ["sample_rail"],
                     "option": {"mode": "rail", "total_minutes": 600, "total_cost_inr": 600, "comfort": 4, "legs": [
                         {"from": "SBC", "to": "MAO", "mode": "rail", "depart": "2026-12-11T21:00:00",
                          "arrive": "2026-12-12T07:00:00", "minutes": 600, "cost_inr": 600}]}}],
        "unavailable": [{"mode": "air", "reason": "no airport"}]})
    assert resp.options[0].option.legs[0].from_ == "SBC"
    assert roundtrip(CompareRequest, {"origin": "Bengaluru", "destination": "Goa"}).modes == ["road", "rail", "air"]
    assert roundtrip(ReviseRequest, {"intent": "lighter_day", "day": "2026-12-12"}).day.day == 12
    assert roundtrip(ReviseRequest, {"intent": "rain"}).day is None
    for bad in ({"intent": "lighter_day"}, {"intent": "swap_stop"}, {"intent": "snow"}):
        with pytest.raises(ValidationError):
            ReviseRequest.model_validate(bad)
    assert roundtrip(PlanText, {"text": "Goa with my parents in December", "lang": "hi"}).lang == "hi"


def test_katha_and_guide_roundtrip():
    roundtrip(KathaStory, {
        "subject_kind": "place", "subject": "Mysore Palace", "length_min": 2, "text": "t",
        "segments": [{"label": "legend", "text": "a"}, {"label": "history", "text": "b"}],
        "sources": ["wikimedia"], "lang": "kn"})
    roundtrip(GuideAnswer, {"text": "t", "citations": [{"title": "T"}], "lang": "hi"})
    roundtrip(KathaStory, {"subject_kind": "place", "subject": "Hampi", "length_min": 5, "text": "t",
                           "segments": [{"label": "disputed", "text": "Two accounts differ."}]})
    req = roundtrip(KathaRequest, {"subject_kind": "day", "subject": "Mysuru day 1", "length_min": 10,
                                   "places": ["mysuru-mysore-palace", "Chamundi Hill"]})
    assert req.lang == "en" and req.places[0] == "mysuru-mysore-palace"
    with pytest.raises(ValidationError):
        KathaRequest.model_validate({"subject_kind": "place", "subject": "", "length_min": 2})


def test_languages():
    assert [x.value for x in Lang] == ["en", "hi", "kn", "ta", "te", "bn"]


def test_rejects_bad_input():
    with pytest.raises(ValidationError):
        TripRequest.model_validate({"origin": "A", "destinations": [], "start_date": "2026-01-01", "end_date": "2026-01-02"})
    with pytest.raises(ValidationError):
        PlanEvent.model_validate({"stage": "bogus", "message": "x"})
    with pytest.raises(ValidationError):
        KathaStory.model_validate({"subject_kind": "place", "subject": "x", "length_min": 3, "text": "t"})


def test_generated_outputs_are_fresh():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_ts.py"), "--check"], check=False)
    assert r.returncode == 0, "run: python packages/contracts/scripts/gen_ts.py"


def test_rejects_out_of_order_dates():
    from ty_contracts import Leg, Stay

    with pytest.raises(ValidationError):
        TripRequest.model_validate({"origin": "A", "destinations": ["B"], "start_date": "2026-01-02", "end_date": "2026-01-01"})
    with pytest.raises(ValidationError):
        Leg.model_validate({"from": "A", "to": "B", "mode": "road", "depart": "2026-01-01T10:00:00",
                            "arrive": "2026-01-01T09:00:00", "minutes": 0, "cost_inr": 0})
    with pytest.raises(ValidationError):
        Stay.model_validate({"name": "n", "city": "c", "check_in": "2026-01-02", "check_out": "2026-01-01",
                             "price_per_night_inr": 1})
