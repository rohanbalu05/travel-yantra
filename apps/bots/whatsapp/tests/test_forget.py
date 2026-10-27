import httpx
import pytest
from test_brain import done, fake_http, sse, text

from app.brain import CONTACT, FORGOTTEN, FORGOTTEN_KEPT, FORGOTTEN_NONE, HELP, Brain

API = "http://api.test"
USER = "15550001111"


def api(delete_status=204, delete_body=None):
    """/plan gives p1, revise gives p2; DELETE /plan/{id} answers delete_status."""
    deleted = []

    def handler(req):
        if req.method == "DELETE":
            deleted.append(req.url.path)
            return httpx.Response(delete_status, json=delete_body)
        if req.url.path == "/plan":
            return httpx.Response(200, text=sse(done()))
        return httpx.Response(200, text=sse({**done(), "plan_id": "p2"}))

    return handler, deleted


@pytest.mark.parametrize(
    "msg",
    ["delete my data", "Please delete all my data", "forget me", "erase my chats", "मेरा डेटा हटाओ"],
)
async def test_delete_my_data_forgets_the_user(monkeypatch, msg):
    handler, deleted = api()
    fake_http(monkeypatch, handler)
    brain = Brain(base=API)
    await brain.handle(text("Plan Bengaluru to Goa 11-14 Dec"))
    await brain.handle(text("rain day 1"))
    reply = await brain.handle(text(msg))
    assert reply == FORGOTTEN.format(n="2 of 2 saved plans")
    assert USER not in brain.users
    assert deleted == ["/plan/p1", "/plan/p2"]
    # A fresh start afterwards: no plan to revise, English help.
    assert await brain.handle(text("hi")) == HELP


async def test_other_users_are_kept(monkeypatch):
    handler, _ = api()
    fake_http(monkeypatch, handler)
    brain = Brain(base=API)
    await brain.handle(text("Plan Bengaluru to Goa 11-14 Dec", user="15550002222"))
    await brain.handle(text("delete my data"))
    assert brain.users["15550002222"].plan_id == "p1"


@pytest.mark.parametrize(
    "status, body",
    [(404, {"detail": "Not Found"}), (405, {"detail": "Method Not Allowed"}), (500, None)],
)
async def test_plans_the_api_cannot_delete_point_to_email(monkeypatch, status, body):
    handler, _ = api(status, body)
    fake_http(monkeypatch, handler)
    brain = Brain(base=API)
    await brain.handle(text("Plan Bengaluru to Goa 11-14 Dec"))
    reply = await brain.handle(text("delete my data"))
    assert reply == FORGOTTEN.format(n="0 of 1 saved plans") + " " + FORGOTTEN_KEPT
    assert CONTACT in reply
    assert USER not in brain.users


async def test_a_plan_already_gone_counts_as_deleted(monkeypatch):
    handler, _ = api(404, {"detail": "plan not found"})
    fake_http(monkeypatch, handler)
    brain = Brain(base=API)
    await brain.handle(text("Plan Bengaluru to Goa 11-14 Dec"))
    assert await brain.handle(text("delete my data")) == FORGOTTEN.format(n="1 of 1 saved plans")


async def test_delete_without_any_state_still_confirms():
    # After a restart the bot holds no plan ids: it says so and points to the email.
    reply = await Brain(base="").handle(text("delete my data"))
    assert reply == FORGOTTEN_NONE + " " + FORGOTTEN_KEPT


@pytest.mark.parametrize(
    "msg",
    [
        "how do I delete photos from my phone?",
        "remove Se Cathedral",
        "forget history, show me food",
        "delete everything on day 2",
    ],
)
def test_not_a_delete_request(msg):
    from app.brain import FORGET

    assert not FORGET.search(msg)
