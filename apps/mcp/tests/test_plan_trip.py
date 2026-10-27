import json

import httpx
from mcp.shared.memory import create_connected_server_and_client_session as connect
from ty_contracts import Itinerary

import server

SAMPLE = json.loads(server.SAMPLE.read_text(encoding="utf-8"))["itinerary"]


async def _call():
    async with connect(server.mcp._mcp_server) as client:
        tools = await client.list_tools()
        assert "plan_trip" in [t.name for t in tools.tools]
        res = await client.call_tool("plan_trip", {"request": SAMPLE["request"]})
        assert not res.isError
        return Itinerary.model_validate(res.structuredContent)


async def test_sample_without_api(monkeypatch):
    monkeypatch.delenv("API_BASE_URL", raising=False)
    it = await _call()
    assert it.request.destinations == ["Goa"]


async def test_calls_api_plan(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://api.test")

    def event(stage, partial):
        return "data: " + json.dumps({"stage": stage, "message": stage, "partial": partial})

    sse = "\n\n".join([event("planning", None), event("done", SAMPLE)]) + "\n\n"

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/plan"
        return httpx.Response(200, text=sse)

    real = httpx.AsyncClient
    monkeypatch.setattr(
        server.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    assert (await _call()).days
