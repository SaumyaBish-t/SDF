"""Storage — DuckDB for metadata, LanceDB for embeddings."""
from __future__ import annotations


class Store:
    async def write(self, example: dict) -> None:
        raise NotImplementedError
