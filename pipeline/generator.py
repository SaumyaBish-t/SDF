"""Generator stage — async batch calls to KEY_1 / KEY_2 producing raw examples."""
from __future__ import annotations


async def generate_batch() -> list[dict]:
    raise NotImplementedError
