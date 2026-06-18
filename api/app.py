"""FastAPI application entrypoint — `uvicorn api.app:app`.

The shared `JobRegistry` lives on `app.state.jobs` and is initialised here.
All long-running work runs inside the orchestrator; this module just wires
routes and logging.
"""
from __future__ import annotations

import os
import platform

# Windows WMI hang guard — MUST run before any scientific-stack import.
# On some Windows hosts `platform._wmi_query` blocks for minutes when the WMI
# service is slow/unresponsive; numpy.testing (pulled in by scipy, pulled in by
# the dedup/diversity stages) calls platform.machine() at import time, which
# stalls the whole API at startup. Short-circuit it — only cosmetic platform
# strings depend on this, and callers already fall back on OSError.
if hasattr(platform, "_wmi_query"):
    def _sdf_no_wmi(*_args, **_kwargs):
        raise OSError("WMI query disabled by SDF to avoid Windows platform import hang")

    platform._wmi_query = _sdf_no_wmi  # type: ignore[attr-defined]

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import JobRegistry, router
from utils import setup_logging


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="Syntropic")
    # Frontend dev server origins. Override with a comma-separated
    # SDF_CORS_ORIGINS for deployed frontends.
    origins = os.getenv(
        "SDF_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.jobs = JobRegistry()
    app.include_router(router)
    return app


app = create_app()
