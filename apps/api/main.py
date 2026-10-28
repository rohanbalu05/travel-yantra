"""Run from apps/api: `uvicorn main:app --port 8080`."""

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from importlib import import_module
from types import ModuleType

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core import router as core_router

log = logging.getLogger(__name__)
# Our loggers print WARNING and up, plus core.llm's per-call token lines (INFO). TY_LOG_LEVEL overrides both.
logging.basicConfig(level=os.getenv("TY_LOG_LEVEL", "WARNING"), format="%(levelname)s %(name)s %(message)s")
logging.getLogger("core.llm").setLevel(os.getenv("TY_LOG_LEVEL", "INFO"))

LANES = ("guide", "routes", "ty_chat")
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


def plain(errors: list[dict], body: object = None) -> str:
    """One plain sentence for a 422 (never pydantic's "Value error, …"): our validators' own sentence, else
    the field and what is wrong with it. /plan takes a form or free text; only the matching one's errors count."""
    kind = "PlanText" if isinstance(body, dict) and "text" in body else "TripRequest"
    def branch(e: dict) -> str:
        loc = e.get("loc", ())
        part = str(loc[1]) if len(loc) > 1 else ""
        return next((k for k in ("PlanText", "TripRequest") if k in part), "")

    errs = [e for e in errors if branch(e) in ("", kind)] or errors
    e = errs[0]
    start = 2 if branch(e) else 1
    msg = str(e.get("msg", "Something in the request is not right"))
    if msg.startswith(("Value error, ", "Assertion failed, ")):
        msg = msg.split(", ", 1)[1]
        return msg if msg.endswith(".") else msg[0].upper() + msg[1:] + "."
    field = " ".join(str(x).replace("_", " ") for x in e.get("loc", ())[start:] if not isinstance(x, int))
    return f"Please check {field}: {msg[0].lower() + msg[1:]}." if field else msg[0].upper() + msg[1:] + "."


@app.exception_handler(RequestValidationError)
async def plain_422(request: Request, exc: RequestValidationError):
    """/plan and its revise, read and delete answer a bad request with a plain sentence the web and chat can
    show as it is; other lanes' routes keep FastAPI's list."""
    if not request.url.path.startswith("/plan"):
        return await request_validation_exception_handler(request, exc)
    return JSONResponse({"detail": plain(list(exc.errors()), exc.body)}, status_code=422)


for name in LANES:
    try:
        module = import_module(name)
        app.include_router(module.router)
        MOUNTED.append(module)
    except Exception:  # a missing or broken lane router must not stop startup
        log.exception("router %s not mounted", name)
