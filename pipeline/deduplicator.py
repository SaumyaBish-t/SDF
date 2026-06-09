"""Two-layer deduplicator — MinHash LSH (syntactic) then LanceDB cosine (semantic).

Layer 1 — MinHash LSH with 5-grams, num_perm=128, Jaccard threshold 0.7
  (FineWeb-Edu settings per PROJECT_SPEC §7). Fast in-memory check that
  catches near-verbatim near-duplicates before we spend an embedding call.

Layer 2 — embed via local sentence-transformers (all-MiniLM-L6-v2),
  query LanceDB for the nearest stored vector. Reject if similarity ≥
  config.SIMILARITY_REJECT (0.92).

  Was originally NIM nv-embedcode-7b-v1 (~2s API round-trip × 100 calls
  per run). Switched to local — first call eats ~3s model-load latency,
  subsequent ones are ~50ms on CPU. Net: ~3 min saved per 100-accept
  run AND one less external dependency.

Survivors are returned as AcceptedExample(embedding=..., minhash_signature=...).
The caller (orchestrator / writer) is responsible for persisting them.

Threading note: datasketch's MinHashLSH is not thread-safe. The pipeline
runs the deduplicator on a single consumer task, so this is fine.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from datasketch import MinHash, MinHashLSH

import config
from models import AcceptedExample, JudgedExample
from storage.store import Store


_log = logging.getLogger("sdf.dedup")


# ---------------------------------------------------------------------------
# Local embedder loader (test seam — monkeypatch this in tests)
# ---------------------------------------------------------------------------
def _make_embedder(model_name: str):
    """Lazily import sentence-transformers and load the model.

    Defined as a module-level function (not a method) so tests can
    `monkeypatch.setattr(dd, "_make_embedder", ...)` and inject a fake
    without pulling the real ~80MB model.
    """
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    return SentenceTransformer(model_name)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def get_ngrams(text: str, n: int = 5) -> list[str]:
    """Character n-grams (lowercased) — the FineWeb-Edu MinHash recipe."""
    s = text.lower()
    if len(s) <= n:
        return [s] if s else []
    return [s[i : i + n] for i in range(len(s) - n + 1)]


def make_minhash(
    text: str, num_perm: int = config.MINHASH_NUM_PERM, n: int = config.MINHASH_NGRAM_SIZE
) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for gram in get_ngrams(text, n):
        m.update(gram.encode("utf-8"))
    return m


def signature_to_list(m: MinHash) -> list[int]:
    """Pydantic-friendly serialization of a MinHash signature."""
    return [int(x) for x in m.hashvalues]


# ---------------------------------------------------------------------------
# Deduplicator
# ---------------------------------------------------------------------------
class Deduplicator:
    """Maintains the MinHash LSH index and bridges to the Store for cosine dedup.

    Construction is sync (no IO). Use `await dedup.check(judged)` per accepted
    JudgedExample; it returns `AcceptedExample` if both layers pass, else None.
    The caller adds the survivor to the LSH index via `register(example_id, text)`
    after writing it to the store — split so callers can decide commit order.
    """

    def __init__(
        self,
        store: Store,
        num_perm: int = config.MINHASH_NUM_PERM,
        ngram_size: int = config.MINHASH_NGRAM_SIZE,
        minhash_threshold: float = config.MINHASH_THRESHOLD,
        similarity_reject: float = config.SIMILARITY_REJECT,
        embed_model: str = config.EMBED_MODEL,
    ):
        self._store = store
        self._num_perm = num_perm
        self._ngram_size = ngram_size
        self._similarity_reject = similarity_reject
        self._embed_model = embed_model
        self._lsh = MinHashLSH(threshold=minhash_threshold, num_perm=num_perm)
        # Lazy-loaded on first embed() call so __init__ stays IO-free —
        # also lets tests construct a Deduplicator without paying the
        # sentence-transformers model-load cost.
        self._embedder = None
        # Stats — useful for the orchestrator to log dup-rate per run.
        self.minhash_rejects = 0
        self.cosine_rejects = 0
        self.accepted = 0

    # -- embedding ----------------------------------------------------------
    def _embed_sync(self, text: str) -> list[float]:
        """Run the local SentenceTransformer encode. Called via to_thread
        so the orchestrator event loop isn't blocked on CPU work."""
        if self._embedder is None:
            self._embedder = _make_embedder(self._embed_model)
        vec = self._embedder.encode(text, convert_to_numpy=True)
        return [float(x) for x in vec]

    async def embed(self, text: str) -> list[float]:
        """One embedding via local sentence-transformers. CPU-bound, so
        offloaded to a thread to keep the event loop responsive."""
        return await asyncio.to_thread(self._embed_sync, text)

    # -- LSH ----------------------------------------------------------------
    def _is_minhash_duplicate(self, m: MinHash) -> bool:
        return len(self._lsh.query(m)) > 0

    def register(self, example_id: str, text: str) -> None:
        """Add a survivor to the LSH index. Idempotent (re-insert is a no-op)."""
        if example_id in self._lsh:
            return
        self._lsh.insert(example_id, make_minhash(text, self._num_perm, self._ngram_size))

    # -- main entry ---------------------------------------------------------
    def _dedup_text(self, judged: JudgedExample) -> str:
        """Text used for both MinHash and embedding — instruction + response.

        Concatenating both lets the dedup catch examples that share an
        instruction but differ in response (and vice versa).
        """
        raw = judged.scored.raw
        return f"{raw.prompt}\n{raw.completion}"

    async def check(self, judged: JudgedExample) -> Optional[AcceptedExample]:
        """Run both dedup layers. Return AcceptedExample on survive, else None.

        Does NOT mutate the LSH index. Call `register(example_id, text)` after
        the example has been persisted to the store so duplicates show up on
        the next call.
        """
        text = self._dedup_text(judged)
        raw = judged.scored.raw

        # Layer 1 — MinHash LSH (cheap; runs in-process)
        sig = await asyncio.to_thread(
            make_minhash, text, self._num_perm, self._ngram_size
        )
        if self._is_minhash_duplicate(sig):
            self.minhash_rejects += 1
            _log.info("dedup: minhash duplicate (example_id=%s)", raw.example_id)
            return None

        # Layer 2 — embedding + LanceDB cosine
        embedding = await self.embed(text)
        if len(embedding) != config.EMBEDDING_DIM:
            raise ValueError(
                f"embedding service returned dim {len(embedding)}, "
                f"expected {config.EMBEDDING_DIM}"
            )
        similarity = await self._store.nearest_similarity(embedding)
        if similarity >= self._similarity_reject:
            self.cosine_rejects += 1
            _log.info(
                "dedup: cosine duplicate (example_id=%s sim=%.4f)",
                raw.example_id, similarity,
            )
            return None

        self.accepted += 1
        return AcceptedExample(
            judged=judged,
            embedding=embedding,
            minhash_signature=signature_to_list(sig),
        )
