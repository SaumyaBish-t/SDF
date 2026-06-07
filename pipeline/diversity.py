"""Diversity metrics + coverage gap analytics for accepted examples.

Two responsibilities (PROJECT_SPEC §6/§7):

  1. Vendi score — semantic diversity of accepted embeddings, computed via
     `vendi_score.vendi.score_dual` on L2-normalized vectors (linear kernel
     on normalized inputs == cosine kernel). Returns the "effective number
     of distinct samples", in [1, n].

  2. Coverage gaps — given a {value: count} dict from `Store.coverage`,
     identify dimension values that fall short of the expected per-value
     count. Used by the API for diagnostics and (eventually) by the
     orchestrator to bias future seed sampling.

Both helpers are pure (no IO) — the orchestrator and API are responsible
for fetching embeddings/coverage from the Store and passing them in.
"""
from __future__ import annotations

import logging
from typing import Sequence

import numpy as np
from vendi_score import vendi


_log = logging.getLogger("sdf.diversity")


# ---------------------------------------------------------------------------
# Vendi score
# ---------------------------------------------------------------------------
def compute_vendi_score(embeddings: Sequence[Sequence[float]]) -> float:
    """Vendi score of an embedding set. Returns 0.0 for n<2 (undefined).

    Uses `score_dual` on L2-normalized vectors so the implicit kernel is
    cosine — matches the dedup layer's similarity metric, so the Vendi
    score measures diversity in the same space dedup operates in.
    """
    n = len(embeddings)
    if n < 2:
        return 0.0
    arr = np.asarray(embeddings, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(f"expected 2-D embeddings array, got shape {arr.shape}")
    # L2-normalize each row; guard against zero vectors.
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    arr = arr / norms
    return float(vendi.score_dual(arr, normalize=False))


# ---------------------------------------------------------------------------
# Coverage gaps
# ---------------------------------------------------------------------------
def coverage_gaps(
    coverage: dict[str, int],
    expected_per_value: int,
) -> dict[str, int]:
    """Return {value: deficit} for values below the expected count.

    `coverage` comes from `Store.coverage(domain, dimension)`. A value
    missing from the dict counts as zero. The returned dict only contains
    values with deficit > 0, sorted descending by deficit so callers can
    prioritize.
    """
    if expected_per_value <= 0:
        return {}
    gaps: list[tuple[str, int]] = []
    for value, count in coverage.items():
        deficit = expected_per_value - int(count)
        if deficit > 0:
            gaps.append((value, deficit))
    gaps.sort(key=lambda kv: kv[1], reverse=True)
    return dict(gaps)


def coverage_deficit_total(
    coverage: dict[str, int], expected_per_value: int
) -> int:
    """Sum of deficits across all values — single-number coverage health."""
    return sum(coverage_gaps(coverage, expected_per_value).values())
