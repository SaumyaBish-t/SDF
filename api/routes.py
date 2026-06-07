"""FastAPI routes — REST layer for kicking off runs and reading status."""
from __future__ import annotations

from fastapi import APIRouter

import config

router = APIRouter()
