"""FastAPI application entrypoint — `uvicorn api.app:app`."""
from __future__ import annotations

from fastapi import FastAPI

from api.routes import router

app = FastAPI(title="Synthetic Data Forge")
app.include_router(router)
