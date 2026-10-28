def test_fastapi_importable():
    import fastapi

    assert fastapi.FastAPI


def test_every_lane_router_is_mounted():
    import main

    assert [m.__name__ for m in main.MOUNTED] == ["guide", "routes", "ty_chat"]
    paths = {r.path for r in main.app.router.routes if hasattr(r, "path")} | set(main.app.openapi()["paths"])
    assert {"/plan", "/guide/ask", "/routes/compare", "/chat"} <= paths
