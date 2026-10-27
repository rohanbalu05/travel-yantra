"""Run from apps/api: `uvicorn main:app --port 8080`."""

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from importlib import import_module
from types import ModuleType

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core import router as core_router

log = logging.getLogger(__name__)

LANES = ("guide", "routes")
MOUNTED: list[ModuleType] = []


def _warm(name: str, fn) -> None:
    started = time.perf_counter()
    try:
        fn()
        # WARNING so it shows in Cloud Run logs at the default level; it is one line per lane per instance.
        log.warning("warm_up %s done in %.1f s", name, time.perf_counter() - started)
    except Exception:  # warming is an optimisation; a failure must not take the API down
        log.exception("warm_up %s failed", name)


def warm_up(modules: list[ModuleType]) -> list[threading.Thread]:
    """Call each lane package's warm_up() (if it has one) in its own daemon thread, so /health and /plan
    answer at once while slow things (the guide's e5 model) load in the background."""
    threads = []
    for mod in modules:
        fn = getattr(mod, "warm_up", None)
        if callable(fn):
            t = threading.Thread(target=_warm, args=(mod.__name__, fn), name=f"warm-{mod.__name__}", daemon=True)
            t.start()
            threads.append(t)
    return threads


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TY_WARM_UP=0 turns warming off (for example in a one-off script).
    if os.getenv("TY_WARM_UP", "1") != "0":
        warm_up(MOUNTED)
    yield


app = FastAPI(title="Travel Yantra API", lifespan=lifespan)
# TY_CORS_ORIGINS: comma-separated extra origins (e.g. the web app's Cloud Run URL). Localhost on any port is always allowed.
ORIGINS = ["https://travel-yantra.web.app", *(o.strip() for o in os.getenv("TY_CORS_ORIGINS", "").split(",") if o.strip())]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(core_router)

for name in LANES:
    try:
        module = import_module(name)
        app.include_router(module.router)
        MOUNTED.append(module)
    except Exception:  # a missing or broken lane router must not stop startup
        log.exception("router %s not mounted", name)
