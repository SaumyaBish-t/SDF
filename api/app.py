"""FastAPI application entrypoint — `uvicorn api.app:app`.

The shared `JobRegistry` lives on `app.state.jobs` and is initialised here.
All long-running work runs inside the orchestrator; this module just wires
routes and logging.
"""
from __future__ import annotations

import os

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
