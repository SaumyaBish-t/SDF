"""Pre-filter critic — KEY_3 / KEY_4 cheap scoring pass."""
from __future__ import annotations


async def prefilter_score(example: dict) -> float:
    raise NotImplementedError
