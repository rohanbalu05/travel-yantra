import json

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect
from ty_contracts import GuideAnswer, Itinerary, KathaStory, TransportOption

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
    done = {"stage": "done", "message": "done", "partial": itinerary}
    return "data: " + json.dumps({"stage": "planning", "message": "p"}) + "\n\ndata: " + json.dumps(
        done
    ) + "\n\n"


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
    it = Itinerary.model_validate(await _call("revise_trip"))
    assert "offline sample: not revised" in it.warnings


async def test_compare_transport_calls_routes_compare(monkeypatch):
    seen = _fake_api(monkeypatch, lambda req: httpx.Response(200, json=SAMPLE["transport"]))
    out = await _call("compare_transport")
    assert seen[0].method == "POST" and seen[0].url.path == "/routes/compare"
    assert json.loads(seen[0].content) == {
        "origin": "Bengaluru",
        "destination": "Panaji",
        "date": "2026-12-11",
    }
    opts = [TransportOption.model_validate(o) for o in out["result"]]
    assert len(opts) == len(SAMPLE["transport"])


async def test_revise_trip_streams_from_plan_revise(monkeypatch):
    seen = _fake_api(monkeypatch, lambda req: httpx.Response(200, text=_sse(SAMPLE)))
    it = Itinerary.model_validate(await _call("revise_trip"))
    assert seen[0].url.path == "/plan/p1/revise"
    assert json.loads(seen[0].content) == {
        "intent": "rain",
        "day": SAMPLE["days"][0]["date"],
        "place_id": None,
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
    assert json.loads(seen[0].content) == {"question": CALLS["ask_guide"]["question"], "lang": "hi"}
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
    _fake_api(monkeypatch, lambda req: httpx.Response(200, text="data: " + json.dumps(ask) + "\n\n"))
    async with connect(server.mcp._mcp_server) as client:
        res = await client.call_tool("plan_trip", CALLS["plan_trip"])
    assert res.isError
    assert "Which dates? How many?" in res.content[0].text
