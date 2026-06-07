"""Tests for pipeline.deduplicator — MinHash layer, cosine layer, embedding."""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import config
from models import JudgedExample, RawExample, ScoredExample
from pipeline import deduplicator as dd
from storage.store import Store


EMBED_DIM = 16  # tests use a small dim; production uses config.EMBEDDING_DIM


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def _judged(example_id: str, prompt: str, completion: str) -> JudgedExample:
    raw = RawExample(
        example_id=example_id,
        node_id="n-0",
        prompt=prompt,
        completion=completion,
        generator_model=config.KEY_1.model,
        generator_key="KEY_1",
    )
    scored = ScoredExample(
        raw=raw,
        prefilter_score=config.PREFILTER_PASS_SCORE,
        prefilter_model=config.KEY_3.model,
        prefilter_key="KEY_3",
    )
    return JudgedExample(
        scored=scored,
        full_score=4.5,
        rubric={d: 4 for d in config.RUBRIC_DIMENSIONS},
        verdict="accept",
    )


class _FakeEmbeddings:
    def __init__(self, vector_for):
        # vector_for is a callable: text -> list[float]
        self._vector_for = vector_for
        self.calls = 0

    async def create(self, *, model: str, input):
        self.calls += 1
        text = input if isinstance(input, str) else input[0]
        return SimpleNamespace(data=[SimpleNamespace(embedding=self._vector_for(text))])


class _FakeClient:
    def __init__(self, vector_for):
        self.embeddings = _FakeEmbeddings(vector_for)


def _patch_embed(monkeypatch, vector_for):
    fake = _FakeClient(vector_for)
    monkeypatch.setattr(dd, "_make_client", lambda _ak: fake)
    async def _no_sleep(_d: float) -> None:
        return None
    monkeypatch.setattr("utils.asyncio.sleep", _no_sleep)
    return fake


@pytest.fixture
async def store(tmp_path: Path):
    s = Store(
        duckdb_path=tmp_path / "meta.duckdb",
        lancedb_path=tmp_path / "lance",
        embedding_dim=EMBED_DIM,
    )
    await s.open()
    yield s
    await s.close()


# Patch EMBEDDING_DIM globally for tests (dedup uses config.EMBEDDING_DIM for validation)
@pytest.fixture(autouse=True)
def _shrink_embedding_dim(monkeypatch):
    monkeypatch.setattr(config, "EMBEDDING_DIM", EMBED_DIM)


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------
def test_get_ngrams_basic() -> None:
    assert dd.get_ngrams("abcdef", n=3) == ["abc", "bcd", "cde", "def"]


def test_get_ngrams_lowercases() -> None:
    assert dd.get_ngrams("ABC", n=2) == ["ab", "bc"]


def test_get_ngrams_short_text_returns_single_token() -> None:
    assert dd.get_ngrams("ab", n=5) == ["ab"]
    assert dd.get_ngrams("", n=5) == []


def test_make_minhash_identical_texts_produce_identical_signatures() -> None:
    a = dd.make_minhash("the quick brown fox jumps")
    b = dd.make_minhash("the quick brown fox jumps")
    assert list(a.hashvalues) == list(b.hashvalues)


def test_make_minhash_different_texts_differ() -> None:
    a = dd.make_minhash("the quick brown fox jumps")
    b = dd.make_minhash("a completely unrelated sentence")
    assert list(a.hashvalues) != list(b.hashvalues)


# ---------------------------------------------------------------------------
# MinHash layer (no API needed)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_minhash_layer_rejects_near_duplicate(store, monkeypatch) -> None:
    _patch_embed(monkeypatch, lambda _t: [0.1] * EMBED_DIM)
    dedup = dd.Deduplicator(store)

    original = "Customer asks about refund policy and wants to return a damaged product."
    accepted = await dedup.check(_judged("ex-1", "Refund?", original))
    assert accepted is not None
    dedup.register("ex-1", f"Refund?\n{original}")

    # Same text → MinHash rejects
    dup = await dedup.check(_judged("ex-2", "Refund?", original))
    assert dup is None
    assert dedup.minhash_rejects == 1
    assert dedup.cosine_rejects == 0


@pytest.mark.asyncio
async def test_minhash_layer_passes_unique_text(store, monkeypatch) -> None:
    _patch_embed(monkeypatch, lambda t: [hash(t) % 100 / 100.0] * EMBED_DIM)
    dedup = dd.Deduplicator(store)

    j1 = _judged("ex-1", "Q1?", "Totally unique completion alpha beta gamma.")
    j2 = _judged("ex-2", "Q2?", "Different content entirely zeta eta theta.")

    a1 = await dedup.check(j1)
    assert a1 is not None
    dedup.register("ex-1", dedup._dedup_text(j1))

    a2 = await dedup.check(j2)
    assert a2 is not None
    assert dedup.minhash_rejects == 0


# ---------------------------------------------------------------------------
# Cosine layer
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cosine_layer_rejects_semantically_identical(
    store, monkeypatch
) -> None:
    """Different surface text, identical embedding → cosine layer should reject."""
    # Force every text to the same vector to simulate semantic identity.
    same_vec = [0.5] * EMBED_DIM
    _patch_embed(monkeypatch, lambda _t: same_vec)
    dedup = dd.Deduplicator(store)

    j1 = _judged("ex-1", "How do I get a refund?", "Visit our returns page within 30 days.")
    accepted = await dedup.check(j1)
    assert accepted is not None
    # Persist embedding so LanceDB can find it on the next query.
    await store.write(accepted, {"domain": "support", "topic": "refund"})
    dedup.register("ex-1", dedup._dedup_text(j1))

    # Wildly different text but same embedding → cosine rejects.
    j2 = _judged("ex-2", "Show me the moon", "Lunar exploration began in 1959.")
    dup = await dedup.check(j2)
    assert dup is None
    assert dedup.cosine_rejects == 1
    assert dedup.minhash_rejects == 0


@pytest.mark.asyncio
async def test_cosine_layer_passes_dissimilar_embedding(
    store, monkeypatch
) -> None:
    # Map text to its hash bucket so each prompt gets a distinct vector.
    # Use md5 (not Python's hash()) because hash() is salted per-process via
    # PYTHONHASHSEED — some salts produce vectors that cross the 0.92 cosine
    # threshold and flake this test.
    def _vec(text: str) -> list[float]:
        digest = int(hashlib.md5(text.encode()).hexdigest(), 16)
        seed = (digest % 1000) / 1000.0
        return [seed + 0.001 * i for i in range(EMBED_DIM)]

    _patch_embed(monkeypatch, _vec)
    dedup = dd.Deduplicator(store)

    j1 = _judged("ex-1", "Alpha", "The first letter.")
    a1 = await dedup.check(j1)
    assert a1 is not None
    await store.write(a1, {"domain": "support", "topic": "first"})
    dedup.register("ex-1", dedup._dedup_text(j1))

    j2 = _judged("ex-2", "Omega", "The last letter in the Greek alphabet system.")
    a2 = await dedup.check(j2)
    assert a2 is not None
    assert dedup.cosine_rejects == 0


# ---------------------------------------------------------------------------
# embed() error path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_embed_dim_mismatch_raises(store, monkeypatch) -> None:
    _patch_embed(monkeypatch, lambda _t: [0.1] * (EMBED_DIM + 3))
    dedup = dd.Deduplicator(store)
    j = _judged("ex-bad", "Q", "A")
    with pytest.raises(ValueError, match="dim"):
        await dedup.check(j)


# ---------------------------------------------------------------------------
# AcceptedExample shape
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_returns_accepted_with_signature_and_embedding(
    store, monkeypatch
) -> None:
    _patch_embed(monkeypatch, lambda _t: [0.42] * EMBED_DIM)
    dedup = dd.Deduplicator(store)
    j = _judged("ex-1", "Q?", "A.")
    accepted = await dedup.check(j)
    assert accepted is not None
    assert len(accepted.embedding) == EMBED_DIM
    assert len(accepted.minhash_signature) == config.MINHASH_NUM_PERM
    assert accepted.judged is j
    assert dedup.accepted == 1


# ---------------------------------------------------------------------------
# register() idempotence
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_register_is_idempotent(store, monkeypatch) -> None:
    _patch_embed(monkeypatch, lambda _t: [0.1] * EMBED_DIM)
    dedup = dd.Deduplicator(store)
    dedup.register("ex-1", "some text content here")
    dedup.register("ex-1", "some text content here")  # second call must not raise
    # Following check with the same text should now be rejected by MinHash.
    j = _judged("ex-2", "any", "some text content here")
    assert await dedup.check(j) is None
