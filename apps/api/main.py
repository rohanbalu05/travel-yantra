"""Run from apps/api: `uvicorn main:app --port 8080`."""

import logging
import os
from importlib import import_module

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core import router as core_router

log = logging.getLogger(__name__)

app = FastAPI(title="Travel Yantra API")
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

for name in ("guide", "routes"):
    try:
        app.include_router(import_module(name).router)
    except Exception:  # a missing or broken lane router must not stop startup
        log.exception("router %s not mounted", name)
