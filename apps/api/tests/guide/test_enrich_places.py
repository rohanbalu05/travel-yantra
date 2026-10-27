import json

import pytest

from guide.places import FIND_HOURS_MASK, MemoryCache, PlacesClient
from guide.scripts import enrich_places as ep

BOM = {"name": "Basilica of Bom Jesus", "lat": 15.50087, "lng": 73.91159,
       "tags": ["hours-unverified", "fee-unverified"], "opens": None, "closes": None,
       "closed_on": []}  # fmt: skip


def _p(day, oh, om, ch, cm, cday=None):
    return {"open": {"day": day, "hour": oh, "minute": om},
            "close": {"day": day if cday is None else cday, "hour": ch, "minute": cm}}  # fmt: skip


def found(periods, lat=15.5009, lng=73.9116, text=None):
    hours = {"periods": periods, "weekdayDescriptions": text or ["Monday: 9:00 AM - 6:30 PM"]}
    return {"id": "ChIJsampleBomJesus0001", "displayName": {"text": "Basilica of Bom Jesus"},
            "location": {"latitude": lat, "longitude": lng}, "regularOpeningHours": hours}  # fmt: skip


def test_enrich_keeps_the_place_id_and_never_the_hours():
    out = ep.enrich(BOM, found([_p(d, 9, 0, 18, 30) for d in range(7)]), "2026-10-28")
    assert out["places_status"] == "hours" and out["place_id"] == "ChIJsampleBomJesus0001"
    assert (out["opens"], out["closes"], out["closed_on"]) == (None, None, [])
    assert "hours_text" not in out and "hours_source" not in out
    assert out["tags"] == ["hours-unverified", "fee-unverified"]
    assert "entry_fee_inr" not in out and "place_id" not in BOM  # input untouched


def test_enrich_strips_hours_an_earlier_run_copied_in():
    old = dict(BOM, opens="09:00", closes="17:00", closed_on=[7], hours_source="google_places",
               hours_text=["Monday: 9 AM-5 PM"], place_id="ChIJold",
               tags=["fee-unverified", "hours-places", "hours-vary"])  # fmt: skip
    out = ep.enrich(old, found([]), "2026-10-28")
    assert (out["opens"], out["closes"], out["closed_on"]) == (None, None, [])
    assert not {"hours_text", "hours_source"} & set(out) and out["place_id"] == "ChIJsampleBomJesus0001"
    assert out["tags"] == ["fee-unverified", "hours-unverified"] and out["places_status"] == "no-hours"
    curated = dict(BOM, opens="10:00", closes="17:30", tags=[])  # a person's hours stay
    assert ep.enrich(curated, None, "2026-10-28")["opens"] == "10:00"


@pytest.mark.parametrize(
    ("hit", "status"),
    [
        (None, "not-found"),
        (found([_p(1, 9, 0, 18, 0)], lat=15.60), "no-match"),  # ~11 km off: another place
        (found([]), "no-hours"),
    ],
)
def test_enrich_marks_what_places_cannot_confirm(hit, status):
    out = ep.enrich(BOM, hit, "2026-10-27")
    assert out["places_status"] == status
    assert out["opens"] is None and "hours-unverified" in out["tags"]
    assert "fee-unverified" in out["tags"] and out["hours_checked"] == "2026-10-27"
    assert ("place_id" in out) == (status == "no-hours")


def test_the_repo_holds_no_places_hours():
    from guide.retrieval.seed import load_pois

    for p in load_pois()["pois"]:
        assert not {"hours_text", "hours_source"} & set(p), p["name"]
        assert not {"hours-places", "hours-break", "hours-vary"} & set(p["tags"]), p["name"]
        if p.get("place_id"):  # Places-matched: hours only at runtime
            assert p["opens"] is None and p["places_status"] in {"hours", "no-hours"}


class Fake:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((url, headers["X-Goog-FieldMask"], body))
        return self.payload


def test_find_with_hours_one_masked_biased_call_then_cache():
    t = Fake({"places": [found([_p(1, 9, 0, 18, 0)])]})
    c = PlacesClient(cache=MemoryCache(), transport=t, api_key="test-key")
    hit = c.find_with_hours("Basilica of Bom Jesus, Goa, India", 15.5, 73.9)
    assert hit["id"] == "ChIJsampleBomJesus0001"
    c.find_with_hours("Basilica of Bom Jesus, Goa, India", 15.5, 73.9)
    assert len(t.calls) == 1
    url, mask, body = t.calls[0]
    assert url.endswith("/places:searchText") and mask == FIND_HOURS_MASK
    assert body["pageSize"] == 1 and body["locationBias"]["circle"]["radius"] == 3000
    assert PlacesClient(transport=Fake({}), api_key="k").find_with_hours("x", 0, 0) is None


def test_budget_stops_calls_and_run_keeps_the_rest(tmp_path, monkeypatch):
    region = tmp_path / "goa_pois.json"
    pois = [dict(BOM, name=f"Place {i}") for i in range(3)]
    region.write_text(json.dumps({"pois": pois}), encoding="utf-8")
    monkeypatch.setattr(ep, "OUT", tmp_path)
    t = ep.CountingTransport(Fake({"places": [found([_p(1, 9, 0, 18, 0)])]}), budget=2)
    client = PlacesClient(cache=MemoryCache(), transport=t, api_key="test-key")
    status = ep.run("goa", client, today="2026-10-27")
    assert t.calls == 2 and status == {"hours": 2, "budget-stop": 1}
    saved = json.loads(region.read_text(encoding="utf-8"))["pois"]
    assert [p.get("places_status") for p in saved] == ["hours", "hours", None]
    t.budget = 10
    status = ep.run("goa", client, today="2026-10-27")  # re-run: only the third is new
    assert status == {"skipped": 2, "hours": 1} and t.calls == 3
