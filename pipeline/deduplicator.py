"""Dedup — MinHash LSH (Jaccard) + LanceDB cosine similarity."""
from __future__ import annotations


async def is_duplicate(example: dict) -> bool:
    raise NotImplementedError
