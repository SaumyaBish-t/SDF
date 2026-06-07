"""Tests for storage.store — DuckDB + LanceDB roundtrip on temp dirs."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

import config
from models import (
    AcceptedExample,
    JudgedExample,
    RawExample,
    ScoredExample,
)
from storage.store import Store


EMBED_DIM = 16  # tiny for tests; production uses config.EMBEDDING_DIM


def _accepted(
    example_id: str = "ex-0",
    score: float = 4.55,
    verdict: str = "accept",
    rubric: dict | None = None,
    vector: list[float] | None = None,
) -> AcceptedExample:
    raw = RawExample(
        example_id=example_id,
        node_id="n-0",
        prompt="What is the refund policy?",
        completion="Within 30 days.",
        generator_model=config.KEY_1.model,
        generator_key="KEY_1",
    )
    scored = ScoredExample(
        raw=raw,
        prefilter_score=config.PREFILTER_PASS_SCORE,
        prefilter_model=config.KEY_3.model,
        prefilter_key="KEY_3",
    )
    judged = JudgedExample(
        scored=scored,
        full_score=score,
        rubric=rubric or {d: 4 for d in config.RUBRIC_DIMENSIONS},
        verdict=verdict,
    )
    return AcceptedExample(
        judged=judged,
        embedding=vector or [0.1] * EMBED_DIM,
        minhash_signature=[1, 2, 3],
    )


def _taxonomy(domain: str = "customer_support", topic: str = "billing_dispute") -> dict[str, str]:
    return {"domain": domain, "topic": topic, "tone": "polite"}


@pytest.fixture
def store_paths(tmp_path: Path):
    return {
        "duckdb_path": tmp_path / "meta.duckdb",
        "lancedb_path": tmp_path / "lance",
    }


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_open_creates_paths_and_tables(store_paths) -> None:
    async with Store(embedding_dim=EMBED_DIM, **store_paths) as store:
        assert store_paths["duckdb_path"].exists()
        assert store_paths["lancedb_path"].exists()
        assert await store.count() == 0


@pytest.mark.asyncio
async def test_reopen_persists_data(store_paths) -> None:
    async with Store(embedding_dim=EMBED_DIM, **store_paths) as s:
        await s.write(_accepted("ex-1"), _taxonomy())
    async with Store(embedding_dim=EMBED_DIM, **store_paths) as s2:
        assert await s2.count() == 1


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_write_persists_row_in_duckdb(store_paths) -> None:
    async with Store(embedding_dim=EMBED_DIM, **store_paths) as store:
        await store.write(_accepted("ex-1", score=4.55), _taxonomy())
        assert await store.count() == 1
        assert await store.count(domain="customer_support") == 1
        assert await store.count(domain="other") == 0


@pytest.mark.asyncio
async def test_write_rejects_wrong_embedding_dim(store_paths) -> None:
    bad = _accepted(vector=[0.1] * (EMBED_DIM + 5))
    async with Store(embedding_dim=EMBED_DIM, **store_paths) as store:
        with pytest.raises(ValueError, match="dim mismatch"):
            await store.write(bad, _taxonomy())


# ---------------------------------------------------------------------------
# nearest_similarity
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_nearest_similarity_empty_store_returns_zero(store_paths) -> None:
    async with Store(embedding_dim=EMBED_DIM, **store_paths) as store:
        assert await store.nearest_similarity([0.1] * EMBED_DIM) == 0.0


@pytest.mark.asyncio
async def test_nearest_similarity_identical_vector_is_one(store_paths) -> None:
    v = [0.5] * EMBED_DIM
    async with Store(embedding_dim=EMBED_DIM, **store_paths) as store:
        await store.write(_accepted("ex-1", vector=v), _taxonomy())
        sim = await store.nearest_similarity(v)
        # Distance ~0 → similarity ~1.0
        assert math.isclose(sim, 1.0, rel_tol=1e-4)


@pytest.mark.asyncio
async def test_nearest_similarity_distant_vector_is_lower(store_paths) -> None:
    near = [0.0] * EMBED_DIM
    far = [10.0] * EMBED_DIM
    async with Store(embedding_dim=EMBED_DIM, **store_paths) as store:
        await store.write(_accepted("ex-1", vector=near), _taxonomy())
        sim_near = await store.nearest_similarity(near)
        sim_far = await store.nearest_similarity(far)
        assert sim_near > sim_far
        assert 0.0 < sim_far < 1.0


@pytest.mark.asyncio
async def test_nearest_similarity_rejects_wrong_dim(store_paths) -> None:
    async with Store(embedding_dim=EMBED_DIM, **store_paths) as store:
        with pytest.raises(ValueError, match="dim"):
            await store.nearest_similarity([0.1] * (EMBED_DIM - 1))


# ---------------------------------------------------------------------------
# coverage analytics
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_coverage_counts_taxonomy_values(store_paths) -> None:
    async with Store(embedding_dim=EMBED_DIM, **store_paths) as store:
        await store.write(_accepted("a"), {"domain": "d", "topic": "billing"})
        await store.write(_accepted("b"), {"domain": "d", "topic": "billing"})
        await store.write(_accepted("c"), {"domain": "d", "topic": "shipping"})
        await store.write(_accepted("e"), {"domain": "other", "topic": "billing"})

        cov = await store.coverage(domain="d", dimension="topic")
        assert cov == {"billing": 2, "shipping": 1}


# ---------------------------------------------------------------------------
# all_embeddings
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_embeddings_returns_every_vector(store_paths) -> None:
    vecs = [[float(i)] * EMBED_DIM for i in range(3)]
    async with Store(embedding_dim=EMBED_DIM, **store_paths) as store:
        for i, v in enumerate(vecs):
            await store.write(_accepted(f"ex-{i}", vector=v), _taxonomy())

        all_v = await store.all_embeddings()
        assert len(all_v) == 3
        retrieved = sorted(int(v[0]) for v in all_v)
        assert retrieved == [0, 1, 2]


@pytest.mark.asyncio
async def test_all_embeddings_filters_by_domain(store_paths) -> None:
    async with Store(embedding_dim=EMBED_DIM, **store_paths) as store:
        await store.write(_accepted("a", vector=[1.0] * EMBED_DIM), {"domain": "d1", "topic": "t"})
        await store.write(_accepted("b", vector=[2.0] * EMBED_DIM), {"domain": "d2", "topic": "t"})

        assert len(await store.all_embeddings(domain="d1")) == 1
        assert len(await store.all_embeddings(domain="d2")) == 1
        assert len(await store.all_embeddings()) == 2
