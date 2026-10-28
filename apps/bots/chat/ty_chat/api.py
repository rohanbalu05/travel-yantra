"""Calls to the Travel Yantra API (plan, revise, guide, katha, delete), in-process inside ty-api.

Without a base URL or an app, answers come from the Goa sample (offline runs and some tests).
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx
from ty_contracts import (
    GuideAnswer,
    GuideQuestion,
    Itinerary,
    KathaRequest,
    KathaStory,
    Lang,
    PlanEvent,
    PlanStage,
    PlanText,
    SavedPlan,
    TripDraft,
)

SAMPLE = Path(__file__).parent / "samples/goa_family.json"
SAMPLE_PLAN_ID = "sample-goa"
Progress = Callable[[PlanEvent], Awaitable[None]]


# Pydantic and FastAPI wording: for the logs, never for the traveller (D-54).
NOT_FOR_USERS = re.compile(
    # TY1's 422s are plain sentences since 0920d57 ("Please check count: input should be ...")
    # and are shown; only FastAPI's list shape and Pydantic's own prefixes are held back.
    r"^(?:validation:|HTTP \d|not found$|method not allowed$|value error|field required|"
    r"assertion failed|extra inputs)",
    re.IGNORECASE,
)


class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail

    @property
    def readable(self) -> bool:
        """A sentence the API wrote for travellers ("Fort Aguada is already on Mon 14 Dec")."""
        return 400 <= self.status < 500 and not NOT_FOR_USERS.search(self.detail)


@dataclass
class Ask:
    """The planner's needs_input: up to three questions and what it understood so far."""

    questions: list[str]
    draft: TripDraft | None = None


@dataclass
class Planned:
    itinerary: Itinerary
    plan_id: str | None
    share_token: str | None
    what: str = ""  # revise: the API's words for what changed


def detail(r: httpx.Response) -> str:
    """The API's own words for an error ("plan not found", a 422's messages)."""
    try:
        d = r.json().get("detail")
    except (ValueError, AttributeError):
        d = None
    if isinstance(d, list):
        d = "validation: " + "; ".join(str(x.get("msg", x)) for x in d if isinstance(x, dict))
    return d if isinstance(d, str) and d else f"HTTP {r.status_code}"


class _Body(httpx.AsyncByteStream):
    def __init__(self, queue: asyncio.Queue, task: asyncio.Task, gone: asyncio.Event) -> None:
        self.queue, self.task, self.gone = queue, task, gone

    async def __aiter__(self):
        while (chunk := await self.queue.get()) is not None:
            yield chunk

    async def aclose(self) -> None:
        self.gone.set()
        if not self.task.done():
            self.task.cancel()


class AsgiStream(httpx.AsyncBaseTransport):
    """Calls an ASGI app in-process and streams its response body as it is sent (httpx's own
    ASGITransport waits for the whole body, which would hide the planner's progress)."""

    def __init__(self, app) -> None:
        self.app = app

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": request.method,
            "scheme": request.url.scheme,
            "path": request.url.path,
            "raw_path": request.url.raw_path.split(b"?")[0],
            "query_string": request.url.query,
            "root_path": "",
            "headers": [(k.lower(), v) for k, v in request.headers.raw],
            "server": (request.url.host, request.url.port or 80),
            "client": ("127.0.0.1", 0),
        }
        queue: asyncio.Queue = asyncio.Queue()
        started: asyncio.Future = asyncio.get_running_loop().create_future()
        gone = asyncio.Event()
        sent = False

        async def receive() -> dict:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            await gone.wait()
            return {"type": "http.disconnect"}

        async def send(msg: dict) -> None:
            if msg["type"] == "http.response.start" and not started.done():
                started.set_result(msg)
            elif msg["type"] == "http.response.body":
                if chunk := msg.get("body", b""):
                    await queue.put(chunk)

        async def run() -> None:
            try:
                await self.app(scope, receive, send)
            except Exception as exc:
                if not started.done():
                    started.set_exception(exc)
            finally:
                if not started.done():
                    started.set_exception(RuntimeError("the app sent no response"))
                await queue.put(None)

        task = asyncio.create_task(run())
        start = await started
        return httpx.Response(
            start["status"], headers=start.get("headers", []), stream=_Body(queue, task, gone)
        )


def _sample(note: str) -> Planned:
    it = Itinerary.model_validate(json.loads(SAMPLE.read_text(encoding="utf-8"))["itinerary"])
    return Planned(it.model_copy(update={"warnings": [*it.warnings, note]}), SAMPLE_PLAN_ID, None)


class Api:
    """`base` is the API's URL ("http://api" in-process with `transport`); empty means offline.
    `headers` are the caller's identity (X-Client-Id, Authorization), forwarded on every call so
    plans belong to the same owner as on the web."""

    def __init__(
        self,
        base: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base = base.rstrip("/")
        self.transport = transport
        self.headers = headers or {}

    @property
    def offline(self) -> bool:
        return not self.base

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base, transport=self.transport, headers=self.headers, timeout=timeout
        )

    async def plan(self, text: str, lang: Lang, progress: Progress | None = None) -> Planned | Ask:
        if self.offline:
            return _sample("offline sample plan")
        body = PlanText(text=text[:4000], lang=lang).model_dump(mode="json")
        return await self._stream("/plan", body, progress)

    async def revise(self, plan_id: str | None, body: dict, progress: Progress | None = None):
        if self.offline or not plan_id or plan_id == SAMPLE_PLAN_ID:
            return _sample("offline sample: not revised")
        result = await self._stream(f"/plan/{quote(plan_id, safe='')}/revise", body, progress)
        if isinstance(result, Ask):  # revise does not ask questions; treat it as a failure
            raise ApiError(422, " ".join(result.questions))
        return result

    async def _stream(self, path: str, body: dict, progress: Progress | None) -> Planned | Ask:
        final, what = None, ""
        async with self._client(150) as client, client.stream("POST", path, json=body) as r:
            if r.is_error:
                await r.aread()
                raise ApiError(r.status_code, detail(r))
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue  # blank separators and ": ping" keep-alives
                event = PlanEvent.model_validate_json(line[5:].strip())
                if event.stage == PlanStage.error:
                    raise ApiError(503 if event.retryable else 500, event.message)
                if event.stage == PlanStage.needs_input:
                    return Ask(event.questions, event.draft)
                if progress is not None:
                    await progress(event)
                if event.stage == PlanStage.solving and event.step is not None and not what:
                    what = event.message
                if event.partial is not None:
                    final = event.partial
                if event.stage == PlanStage.done:
                    if final is None:
                        break
                    return Planned(final, event.plan_id, event.share_token, what)
        raise ApiError(500, "plan finished without an itinerary")

    async def saved(self, plan_id: str) -> tuple[Itinerary, str] | None:
        """GET /plan/{plan_id} (the owner's own plan): its itinerary and share token."""
        if self.offline:
            return None
        async with self._client(20) as client:
            r = await client.get(f"/plan/{quote(plan_id, safe='')}")
        if not r.is_success:
            return None
        saved = SavedPlan.model_validate(r.json())
        return saved.itinerary, saved.share_token

    async def shared(self, token: str) -> Itinerary | None:
        """GET /trips/{share_token}: the plan a web page shows, so chat edits apply to it."""
        if self.offline:
            return None
        async with self._client(20) as client:
            r = await client.get(f"/trips/{quote(token, safe='')}")
        return Itinerary.model_validate(r.json()) if r.is_success else None

    async def ask(self, q: GuideQuestion) -> GuideAnswer:
        if self.offline:
            return GuideAnswer(text=f"(offline sample) I would ask the guide: {q.question}")
        async with self._client(60) as client:
            r = await client.post("/guide/ask", json=q.model_dump(mode="json", exclude_none=True))
        if r.is_error:
            raise ApiError(r.status_code, detail(r))
        return GuideAnswer.model_validate(r.json())

    async def katha(self, req: KathaRequest) -> KathaStory:
        if self.offline:
            return KathaStory(
                subject_kind=req.subject_kind,
                subject=req.subject,
                length_min=req.length_min,
                text=f"(offline sample) I would tell the story of {req.subject}.",
            )
        async with self._client(120) as client:
            r = await client.post("/guide/katha", json=req.model_dump(mode="json"))
        if r.is_error:
            raise ApiError(r.status_code, detail(r))
        return KathaStory.model_validate(r.json())

    async def delete_plan(self, plan_id: str) -> bool:
        """DELETE /plan/{plan_id}; a 404 means it is already gone. False when it failed."""
        if self.offline or plan_id == SAMPLE_PLAN_ID:
            return True
        try:
            async with self._client(20) as client:
                r = await client.delete(f"/plan/{quote(plan_id, safe='')}")
        except httpx.HTTPError:
            return False
        return r.is_success or (r.status_code == 404 and detail(r) != "Not Found")
