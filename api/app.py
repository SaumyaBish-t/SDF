"""FastAPI application entrypoint — `uvicorn api.app:app`.

The shared `JobRegistry` lives on `app.state.jobs` and is initialised here.
All long-running work runs inside the orchestrator; this module just wires
routes and logging.
"""
from __future__ import annotations

from fastapi import FastAPI

from api.routes import JobRegistry, router
from utils import setup_logging


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="Synthetic Data Forge")
    app.state.jobs = JobRegistry()
    app.include_router(router)
    return app


app = create_app()
