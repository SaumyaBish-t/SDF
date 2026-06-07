"""Persistence layer — DuckDB for metadata analytics, LanceDB for vectors.

DuckDB stores one row per accepted example with the full rubric + taxonomy
metadata as JSON blobs (queryable via `json_extract`). LanceDB stores the
embedding + just enough metadata to support semantic dedup lookups.

Both libraries are synchronous; we run their calls inside `asyncio.to_thread`
so the orchestrator's event loop is never blocked on disk IO.

See PROJECT_SPEC.md §8 for the schema rationale and example analytics queries.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import duckdb
import lancedb
import pyarrow as pa

import config
from models import AcceptedExample


_log = logging.getLogger("sdf.store")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
_DUCKDB_SCHEMA = """
CREATE TABLE IF NOT EXISTS examples (
    id                  VARCHAR PRIMARY KEY,
    domain              VARCHAR NOT NULL,
    instruction         VARCHAR NOT NULL,
    response            VARCHAR NOT NULL,
    composite_score     DOUBLE  NOT NULL,
    verdict             VARCHAR NOT NULL,
    rubric_json         VARCHAR NOT NULL,   -- JSON blob, queryable via json_extract
    taxonomy_node_json  VARCHAR NOT NULL,   -- JSON blob
    generator_model     VARCHAR NOT NULL,
    generator_key       VARCHAR NOT NULL,
    prefilter_key       VARCHAR NOT NULL,
    prefilter_score     DOUBLE  NOT NULL,
    timestamp           TIMESTAMP NOT NULL
);
"""


def _lance_schema(embedding_dim: int) -> pa.Schema:
    return pa.schema([
        pa.field("id",              pa.string()),
        pa.field("domain",          pa.string()),
        pa.field("vector",          pa.list_(pa.float32(), embedding_dim)),
        pa.field("composite_score", pa.float64()),
    ])


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------
class Store:
    """DuckDB + LanceDB persistence. Use as an async context manager.

    Example:
        async with Store() as store:
            await store.write(accepted_example, node_set_dimensions={"topic": "..."})
            sim = await store.nearest_similarity(query_vector)
    """

    def __init__(
        self,
        duckdb_path: Optional[Path] = None,
        lancedb_path: Optional[Path] = None,
        embedding_dim: Optional[int] = None,
    ):
        self._duckdb_path = duckdb_path or config.DUCKDB_PATH
        self._lancedb_path = lancedb_path or config.LANCEDB_PATH
        self._embedding_dim = embedding_dim or config.EMBEDDING_DIM
        self._duck: Optional[duckdb.DuckDBPyConnection] = None
        self._lance_table = None  # lancedb.Table

    # -- lifecycle ----------------------------------------------------------
    def _open_sync(self) -> None:
        self._duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        self._lancedb_path.mkdir(parents=True, exist_ok=True)

        self._duck = duckdb.connect(str(self._duckdb_path))
        self._duck.execute(_DUCKDB_SCHEMA)

        lance_db = lancedb.connect(str(self._lancedb_path))
        schema = _lance_schema(self._embedding_dim)
        # lancedb API shifted across versions:
        #   ~0.13: table_names() -> list[str]
        #   newer: list_tables() -> list[str] or ListTablesResponse(tables=[...])
        lister = getattr(lance_db, "list_tables", None) or lance_db.table_names
        result = lister()
        names = getattr(result, "tables", result)  # unwrap response object
        existing = set(names)
        if config.LANCE_TABLE_NAME in existing:
            self._lance_table = lance_db.open_table(config.LANCE_TABLE_NAME)
        else:
            self._lance_table = lance_db.create_table(
                config.LANCE_TABLE_NAME, schema=schema
            )

    async def open(self) -> "Store":
        await asyncio.to_thread(self._open_sync)
        _log.info(
            "store opened: duckdb=%s lancedb=%s dim=%d",
            self._duckdb_path, self._lancedb_path, self._embedding_dim,
        )
        return self

    def _close_sync(self) -> None:
        if self._duck is not None:
            self._duck.close()
            self._duck = None
        # lancedb tables don't need explicit close.
        self._lance_table = None

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    async def __aenter__(self) -> "Store":
        return await self.open()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    # -- write --------------------------------------------------------------
    def _write_sync(
        self, accepted: AcceptedExample, taxonomy_node: dict[str, str]
    ) -> None:
        assert self._duck is not None and self._lance_table is not None
        raw = accepted.judged.scored.raw
        if len(accepted.embedding) != self._embedding_dim:
            raise ValueError(
                f"embedding dim mismatch: got {len(accepted.embedding)}, "
                f"expected {self._embedding_dim}"
            )

        self._duck.execute(
            "INSERT INTO examples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                raw.example_id,
                taxonomy_node.get("domain", ""),  # domain stored on NodeSet
                raw.prompt,
                raw.completion,
                accepted.judged.full_score,
                accepted.judged.verdict,
                json.dumps(accepted.judged.rubric, ensure_ascii=False),
                json.dumps(taxonomy_node, ensure_ascii=False),
                raw.generator_model,
                raw.generator_key,
                accepted.judged.scored.prefilter_key,
                accepted.judged.scored.prefilter_score,
                datetime.now(timezone.utc),
            ],
        )

        self._lance_table.add([{
            "id":              raw.example_id,
            "domain":          taxonomy_node.get("domain", ""),
            "vector":          [float(x) for x in accepted.embedding],
            "composite_score": accepted.judged.full_score,
        }])

    async def write(
        self, accepted: AcceptedExample, taxonomy_node: dict[str, str]
    ) -> None:
        """Persist one accepted example to both stores.

        `taxonomy_node` is the NodeSet.dimensions dict augmented with
        `{"domain": ...}` — the orchestrator passes it because RawExample
        doesn't carry the domain (only the node_id).
        """
        await asyncio.to_thread(self._write_sync, accepted, taxonomy_node)

    # -- query --------------------------------------------------------------
    def _nearest_similarity_sync(self, embedding: list[float]) -> float:
        assert self._lance_table is not None
        if len(embedding) != self._embedding_dim:
            raise ValueError(
                f"query embedding dim {len(embedding)} != store dim {self._embedding_dim}"
            )
        # Empty index → no neighbors → similarity 0.0
        if self._lance_table.count_rows() == 0:
            return 0.0
        results = (
            self._lance_table.search([float(x) for x in embedding])
            .limit(1)
            .to_list()
        )
        if not results:
            return 0.0
        # LanceDB returns _distance (L2 by default). For unit-norm vectors,
        # cosine_similarity = 1 - distance^2 / 2. We expose 1/(1+distance)
        # as a monotonic proxy that lives in (0, 1] — good enough for
        # threshold comparisons the dedup stage owns.
        distance = float(results[0].get("_distance", 0.0))
        return 1.0 / (1.0 + distance)

    async def nearest_similarity(self, embedding: list[float]) -> float:
        """Return a (0, 1] similarity score for the closest stored vector. 0 if empty."""
        return await asyncio.to_thread(self._nearest_similarity_sync, embedding)

    def _count_sync(self, domain: Optional[str]) -> int:
        assert self._duck is not None
        if domain is None:
            row = self._duck.execute("SELECT COUNT(*) FROM examples").fetchone()
        else:
            row = self._duck.execute(
                "SELECT COUNT(*) FROM examples WHERE domain = ?", [domain]
            ).fetchone()
        return int(row[0]) if row else 0

    async def count(self, domain: Optional[str] = None) -> int:
        """Total persisted examples, optionally filtered by domain."""
        return await asyncio.to_thread(self._count_sync, domain)

    def _coverage_sync(self, domain: str, dimension: str) -> dict[str, int]:
        assert self._duck is not None
        # json_extract returns a JSON string ("\"value\"") — strip surrounding quotes.
        rows = self._duck.execute(
            f"""
            SELECT json_extract(taxonomy_node_json, '$.{dimension}') AS val,
                   COUNT(*) AS n
            FROM examples
            WHERE domain = ?
            GROUP BY val
            """,
            [domain],
        ).fetchall()
        out: dict[str, int] = {}
        for val, n in rows:
            if val is None:
                continue
            key = val.strip('"') if isinstance(val, str) else str(val)
            out[key] = int(n)
        return out

    async def coverage(self, domain: str, dimension: str) -> dict[str, int]:
        """{value: count} for one taxonomy dimension within a domain."""
        return await asyncio.to_thread(self._coverage_sync, domain, dimension)

    def _all_embeddings_sync(self, domain: Optional[str]) -> list[list[float]]:
        assert self._lance_table is not None
        df = self._lance_table.to_arrow().to_pylist()
        if domain is None:
            return [row["vector"] for row in df]
        return [row["vector"] for row in df if row["domain"] == domain]

    async def all_embeddings(self, domain: Optional[str] = None) -> list[list[float]]:
        """Return every stored embedding (optionally filtered by domain).

        Used by the diversity tracker (Vendi Score) — not for the dedup hot path.
        """
        return await asyncio.to_thread(self._all_embeddings_sync, domain)
