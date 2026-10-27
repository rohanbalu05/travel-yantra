import json

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect
from ty_contracts import CompareRequest, CompareResponse, GuideAnswer, Itinerary, KathaStory

import server

SAMPLE = json.loads(server.SAMPLE.read_text(encoding="utf-8"))["itinerary"]
OFFLINE = json.loads(server.OFFLINE.read_text(encoding="utf-8"))
TOOLS = ["plan_trip", "compare_transport", "revise_trip", "get_katha", "ask_guide", "track_booking"]

CALLS = {
    "plan_trip": {"request": SAMPLE["request"]},
    "compare_transport": {"origin": "Bengaluru", "destination": "Panaji", "on": "2026-12-11"},
    "revise_trip": {"plan_id": "p1", "intent": "rain", "day": SAMPLE["days"][0]["date"]},
    "get_katha": {"place_id": "goa-basilica", "length": 5},
    "ask_guide": {"question": "What should we eat in Panaji?", "lang": "hi"},
    "track_booking": {"pnr": "1234567890"},
}


async def _call(name):
    async with connect(server.mcp._mcp_server) as client:
        res = await client.call_tool(name, CALLS[name])
        assert not res.isError, res.content
        return res.structuredContent


def _fake_api(monkeypatch, handler):
    monkeypatch.setenv("API_BASE_URL", "http://api.test/")
    seen = []

    def record(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    real = httpx.AsyncClient
    monkeypatch.setattr(
        server.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(record), **kw)
    )
    return seen


def _sse(itinerary):
    done = {"stage": "done", "message": "done", "partial": itinerary, "plan_id": "p2"}
    return (
        "data: "
        + json.dumps({"stage": "planning", "message": "p"})
        + "\n\ndata: "
        + json.dumps(done)
        + "\n\n"
    )


async def test_lists_all_six_tools():
    async with connect(server.mcp._mcp_server) as client:
        tools = await client.list_tools()
    assert [t.name for t in tools.tools] == TOOLS


@pytest.mark.parametrize("name", TOOLS)
async def test_each_tool_answers_offline(monkeypatch, name):
    monkeypatch.delenv("API_BASE_URL", raising=False)
    assert await _call(name)


async def test_offline_revise_says_it_did_not_revise(monkeypatch):
    monkeypatch.delenv("API_BASE_URL", raising=False)
    it = Itinerary.model_validate((await _call("revise_trip"))["itinerary"])
    assert "offline sample: not revised" in it.warnings


async def test_compare_transport_calls_routes_compare(monkeypatch):
    offline = server._sample_compare(CompareRequest(origin="x", destination="y"))
    offline = offline.model_dump(mode="json", by_alias=True)
    seen = _fake_api(monkeypatch, lambda req: httpx.Response(200, json=offline))
    out = CompareResponse.model_validate(await _call("compare_transport"))
    assert seen[0].method == "POST" and seen[0].url.path == "/routes/compare"
    body = json.loads(seen[0].content)
    assert (body["origin"], body["destination"], body["date"]) == (
        "Bengaluru",
        "Panaji",
        "2026-12-11",
    )
    assert body["rank_by"] == "balanced" and body["travellers"] == 1
    assert [o.rank for o in out.options] == list(range(1, len(SAMPLE["transport"]) + 1))


async def test_revise_trip_streams_from_plan_revise(monkeypatch):
    seen = _fake_api(monkeypatch, lambda req: httpx.Response(200, text=_sse(SAMPLE)))
    it = Itinerary.model_validate((await _call("revise_trip"))["itinerary"])
    assert seen[0].url.path == "/plan/p1/revise"
    assert json.loads(seen[0].content) == {
        "intent": "rain",
        "day": SAMPLE["days"][0]["date"],
        "lang": "en",
    }
    assert it.days


async def test_revise_trip_raises_on_error_event(monkeypatch):
    err = "data: " + json.dumps({"stage": "error", "message": "no indoor stops"}) + "\n\n"
    _fake_api(monkeypatch, lambda req: httpx.Response(200, text=err))
    async with connect(server.mcp._mcp_server) as client:
        res = await client.call_tool("revise_trip", CALLS["revise_trip"])
    assert res.isError
    assert "no indoor stops" in res.content[0].text


async def test_get_katha_calls_guide_katha(monkeypatch):
    seen = _fake_api(monkeypatch, lambda req: httpx.Response(200, json=OFFLINE["katha"]))
    story = KathaStory.model_validate(await _call("get_katha"))
    assert seen[0].url.path == "/guide/katha"
    assert dict(seen[0].url.params) == {"place_id": "goa-basilica", "length": "5"}
    assert {s.label for s in story.segments} == {"legend", "history"}


async def test_ask_guide_calls_guide_ask(monkeypatch):
    seen = _fake_api(monkeypatch, lambda req: httpx.Response(200, json=OFFLINE["guide"]))
    ans = GuideAnswer.model_validate(await _call("ask_guide"))
    assert seen[0].method == "POST" and seen[0].url.path == "/guide/ask"
    assert json.loads(seen[0].content) == {
        "question": CALLS["ask_guide"]["question"],
        "lang": "hi",
        "has_elderly": False,
    }
    assert ans.citations


async def test_track_booking_calls_pnr_mock(monkeypatch):
    seen = _fake_api(monkeypatch, lambda req: httpx.Response(200, json=OFFLINE["pnr"]))
    out = await _call("track_booking")
    assert seen[0].url.path == "/routes/pnr-mock"
    assert seen[0].url.params["pnr"] == "1234567890"
    assert out["timeline"][-1]["status"] == "CNF"


async def test_api_error_surfaces_as_tool_error(monkeypatch):
    _fake_api(monkeypatch, lambda req: httpx.Response(503))
    async with connect(server.mcp._mcp_server) as client:
        res = await client.call_tool("ask_guide", CALLS["ask_guide"])
    assert res.isError


async def test_plan_needs_input_surfaces_questions(monkeypatch):
    ask = {"stage": "needs_input", "message": "q", "questions": ["Which dates?", "How many?"]}
    _fake_api(
        monkeypatch, lambda req: httpx.Response(200, text="data: " + json.dumps(ask) + "\n\n")
    )
    async with connect(server.mcp._mcp_server) as client:
        res = await client.call_tool("plan_trip", CALLS["plan_trip"])
    assert res.isError
    assert "Which dates? How many?" in res.content[0].text


async def test_revise_trip_escapes_plan_id(monkeypatch):
    seen = _fake_api(monkeypatch, lambda req: httpx.Response(200, text=_sse(SAMPLE)))
    async with connect(server.mcp._mcp_server) as client:
        await client.call_tool("revise_trip", {**CALLS["revise_trip"], "plan_id": "../admin?x=1"})
    assert seen[0].url.raw_path == b"/plan/..%2Fadmin%3Fx%3D1/revise"


async def test_plan_trip_returns_plan_id(monkeypatch):
    sse = ": ping\n\n" + _sse(SAMPLE)
    _fake_api(monkeypatch, lambda req: httpx.Response(200, text=sse))
    out = await _call("plan_trip")
    assert out["plan_id"] == "p2"
    assert Itinerary.model_validate(out["itinerary"]).days


async def test_offline_plan_id_works_with_offline_revise(monkeypatch):
    monkeypatch.delenv("API_BASE_URL", raising=False)
    planned = await _call("plan_trip")
    assert planned["plan_id"] == server.SAMPLE_PLAN_ID


def _tagging(req: httpx.Request) -> httpx.Response:
    body = json.loads(req.content)
    outs = [f"<{body['target']}>{t}" for t in body["texts"]]
    return httpx.Response(
        200,
        json={
            "translations": outs,
            "target": body["target"],
            "via": [],
            "flags": [[] for _ in outs],
        },
    )


async def test_ask_guide_translates_text_only_and_sends_location(monkeypatch):
    answer = {"text": "Fish curry [1].", "citations": [{"title": "Goan food"}], "lang": "en"}
    monkeypatch.setenv("TRANSLATE_URL", "http://translate.test")
    seen = _fake_api(
        monkeypatch,
        lambda req: (
            _tagging(req) if req.url.host == "translate.test" else httpx.Response(200, json=answer)
        ),
    )
    async with connect(server.mcp._mcp_server) as client:
        res = await client.call_tool(
            "ask_guide", {"question": "nearest hospital", "lang": "ta", "lat": 15.5, "lng": 73.8}
        )
    out = GuideAnswer.model_validate(res.structuredContent)
    body = json.loads(seen[0].content)
    assert (body["lat"], body["lng"], body["lang"]) == (15.5, 73.8, "ta")
    assert "[1]" in json.loads(seen[1].content)["entities"]
    assert out.text == "<ta>Fish curry [1]." and out.lang == "ta"
    assert out.citations[0].title == "Goan food"


async def test_ask_guide_stays_english_without_translate(monkeypatch):
    monkeypatch.delenv("TRANSLATE_URL", raising=False)
    _fake_api(monkeypatch, lambda req: httpx.Response(200, json=OFFLINE["guide"]))
    out = GuideAnswer.model_validate(await _call("ask_guide"))
    assert out.text == OFFLINE["guide"]["text"] and out.lang == "en"


async def test_get_katha_translates_text_and_segments(monkeypatch):
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.setenv("TRANSLATE_URL", "http://translate.test")
    real = httpx.AsyncClient  # one patch covers the translate client too (same httpx module)
    monkeypatch.setattr(
        server.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(_tagging), **kw),
    )
    sent = []
    monkeypatch.setattr(
        server.httpx,
        "AsyncClient",
        lambda **kw: real(
            transport=httpx.MockTransport(lambda req: sent.append(req) or _tagging(req)), **kw
        ),
    )
    async with connect(server.mcp._mcp_server) as client:
        res = await client.call_tool("get_katha", {"place_id": "goa-basilica", "lang": "kn"})
    assert len(sent) == 1  # text and segments in one translate call
    story = KathaStory.model_validate(res.structuredContent)
    assert story.lang == "kn" and story.text.startswith("<kn>")
    assert all(s.text.startswith("<kn>") for s in story.segments)
    assert story.sources == OFFLINE["katha"]["sources"]


async def test_api_4xx_detail_is_the_tool_error(monkeypatch):
    _fake_api(monkeypatch, lambda req: httpx.Response(404, json={"detail": "unknown sample PNR"}))
    async with connect(server.mcp._mcp_server) as client:
        res = await client.call_tool("track_booking", CALLS["track_booking"])
    assert res.isError
    assert "unknown sample PNR" in res.content[0].text


async def test_revise_unknown_plan_shows_api_detail(monkeypatch):
    _fake_api(monkeypatch, lambda req: httpx.Response(404, json={"detail": "unknown plan_id"}))
    async with connect(server.mcp._mcp_server) as client:
        res = await client.call_tool("revise_trip", CALLS["revise_trip"])
    assert res.isError and "unknown plan_id" in res.content[0].text


async def test_revise_422_messages_are_joined(monkeypatch):
    body = {"detail": [{"msg": "lighter_day needs day"}, {"msg": "day not in plan"}]}
    _fake_api(monkeypatch, lambda req: httpx.Response(422, json=body))
    async with connect(server.mcp._mcp_server) as client:
        res = await client.call_tool("revise_trip", CALLS["revise_trip"])
    assert res.isError and "lighter_day needs day; day not in plan" in res.content[0].text
