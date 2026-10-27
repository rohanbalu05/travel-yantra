"""The OpenClaw skill: SKILL.md frontmatter, mcp.json, and scripts/ty.py against a fake API."""

import importlib.util
import io
import json
import re
import urllib.error
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "openclaw/travel-yantra"
SAMPLE = json.loads(
    (Path(__file__).resolve().parents[1] / "samples/goa_family.json").read_text("utf-8")
)

spec = importlib.util.spec_from_file_location("ty_skill", SKILL / "scripts/ty.py")
ty = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ty)


def frontmatter() -> dict[str, str]:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "SKILL.md must start with --- frontmatter ---"
    return dict(line.split(": ", 1) for line in m[1].splitlines())


def test_frontmatter_has_name_description_and_gating():
    fm = frontmatter()
    assert fm["name"] == "travel-yantra" == SKILL.name
    assert len(fm["description"]) > 50
    meta = json.loads(fm["metadata"])  # single-line JSON parses under OpenClaw's YAML and JSON5
    assert meta["openclaw"]["requires"]["bins"] == ["python3"]


def test_skill_names_only_real_commands():
    body = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "{baseDir}/scripts/ty.py" in body
    commands = set(ty.parser()._subparsers._group_actions[0].choices)
    assert commands == {"plan", "revise", "compare", "katha", "ask", "pnr"}
    for cmd in commands:
        assert f"`{cmd} " in body


def test_mcp_json_points_at_the_mcp_path():
    server = json.loads((SKILL / "mcp.json").read_text("utf-8"))["mcp"]["servers"]["travel-yantra"]
    assert server["url"].endswith("/mcp") and server["transport"] == "streamable-http"


class Fake:
    """urlopen stand-in: records requests, answers from a handler(req) -> (status, bytes)."""

    def __init__(self, handler):
        self.handler, self.seen = handler, []

    def __call__(self, req, timeout):
        self.seen.append(req)
        status, body = self.handler(req)
        if status >= 400:
            raise urllib.error.HTTPError(req.full_url, status, "err", {}, io.BytesIO(body))
        return _Resp(body)


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def sse(*events: dict) -> bytes:
    return "".join(f": ping\n\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def done(**extra) -> dict:
    return {"stage": "done", "message": "done", "partial": SAMPLE["itinerary"], **extra}


def run(argv, handler, capsys, monkeypatch):
    monkeypatch.setenv("TRAVEL_YANTRA_API", "http://api.test/")
    monkeypatch.setenv("TRAVEL_YANTRA_WEB", "http://web.test")
    fake = Fake(handler)
    code = ty.main(argv, opener=fake)
    return code, json.loads(capsys.readouterr().out), fake.seen


def test_plan_streams_to_the_itinerary_and_share_link(capsys, monkeypatch):
    handler = lambda req: (200, sse(done(plan_id="p1", share_token="s1")))
    code, out, [req] = run(
        ["plan", "Bengaluru to Goa, 11-14 Dec", "--lang", "hi"], handler, capsys, monkeypatch
    )
    assert code == 0 and req.full_url == "http://api.test/plan"
    assert json.loads(req.data) == {"text": "Bengaluru to Goa, 11-14 Dec", "lang": "hi"}
    assert out["plan_id"] == "p1" and out["share_url"] == "http://web.test/t/s1/"
    assert out["itinerary"]["days"]


def test_plan_needs_input_returns_the_questions(capsys, monkeypatch):
    ask = {"stage": "needs_input", "message": "q", "questions": ["Which dates?"]}
    code, out, _ = run(["plan", "Goa trip"], lambda req: (200, sse(ask)), capsys, monkeypatch)
    assert code == 0 and out["needs_input"] == ["Which dates?"]


def test_plan_error_event_exits_1(capsys, monkeypatch):
    err = {"stage": "error", "message": "no route"}
    code, out, _ = run(["plan", "Goa trip"], lambda req: (200, sse(err)), capsys, monkeypatch)
    assert code == 1 and out == {"error": "no route"}


def test_revise_quotes_the_plan_id_and_sends_only_given_fields(capsys, monkeypatch):
    handler = lambda req: (200, sse(done(plan_id="p2")))
    code, out, [req] = run(
        ["revise", "../p1?x", "move_day", "--city", "Mysuru"], handler, capsys, monkeypatch
    )
    assert req.full_url == "http://api.test/plan/..%2Fp1%3Fx/revise"
    assert json.loads(req.data) == {"intent": "move_day", "city": "Mysuru", "lang": "en"}
    assert code == 0 and out["plan_id"] == "p2" and out["share_url"] is None


def test_compare_katha_ask_and_pnr_bodies(capsys, monkeypatch):
    handler = lambda req: (200, b'{"ok": true}')
    _, _, [c] = run(
        ["compare", "Bengaluru", "Mysuru", "--on", "2026-10-31"], handler, capsys, monkeypatch
    )
    assert c.full_url.endswith("/routes/compare")
    assert json.loads(c.data) == {
        "origin": "Bengaluru",
        "destination": "Mysuru",
        "date": "2026-10-31",
        "rank_by": "balanced",
        "travellers": 1,
    }
    _, _, [k] = run(["katha", "Mysore Palace", "--lang", "hi"], handler, capsys, monkeypatch)
    assert json.loads(k.data) == {
        "subject_kind": "place",
        "subject": "Mysore Palace",
        "length_min": 2,
        "lang": "hi",
    }
    _, _, [a] = run(
        ["ask", "nearest hospital", "--lat", "15.5", "--lng", "73.8"], handler, capsys, monkeypatch
    )
    assert json.loads(a.data) == {
        "question": "nearest hospital",
        "lang": "en",
        "lat": 15.5,
        "lng": 73.8,
    }
    _, _, [p] = run(["pnr", "1234567890"], handler, capsys, monkeypatch)
    assert (
        p.get_method() == "GET" and p.full_url == "http://api.test/routes/pnr-mock?pnr=1234567890"
    )


def test_api_error_detail_is_printed_and_exits_1(capsys, monkeypatch):
    handler = lambda req: (404, b'{"detail": "No story for that place yet."}')
    code, out, _ = run(["katha", "Atlantis"], handler, capsys, monkeypatch)
    assert code == 1 and out == {"error": "HTTP 404: No story for that place yet."}


def test_bad_arguments_are_refused_before_any_call(monkeypatch):
    with pytest.raises(SystemExit):
        ty.main(["katha", "Hampi", "--minutes", "7"], opener=Fake(lambda req: (200, b"{}")))
