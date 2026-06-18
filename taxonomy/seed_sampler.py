"""Seed sampler — draws N NodeSets with min-coverage guarantees.

A NodeSet is one value per dimension. We do NOT enumerate the full cartesian
product (it explodes — 5×4×3×3×3 = 540 for customer_support, far worse for
realistic taxonomies). Instead we sample N node-sets while guaranteeing
every value in every dimension appears at least `min_coverage` times.

Algorithm (per dimension, independent):
  1. Build a "required pool" = each value repeated `min_coverage` times, shuffled.
  2. For the first len(pool) picks, pop from the pool (guarantees coverage).
  3. For remaining picks (n - len(pool)), choose uniformly at random.

If n < len(values) * min_coverage for any dimension, coverage cannot be met
and we raise CoverageError unless `strict=False`.
"""
from __future__ import annotations

import random
from typing import Optional

from models import NodeSet
from taxonomy.builder import Taxonomy


class CoverageError(ValueError):
    """Raised when n is too small to give every dimension value min_coverage."""


def _build_dim_sequence(
    values: list[str], n: int, min_coverage: int, rng: random.Random
) -> list[str]:
    pool: list[str] = [v for v in values for _ in range(min_coverage)]
    rng.shuffle(pool)

    if n <= len(pool):
        return pool[:n]
    extra = [rng.choice(values) for _ in range(n - len(pool))]
    return pool + extra


def sample_node_sets(
    taxonomy: Taxonomy,
    domain: str,
    n: int,
    min_coverage: int = 3,
    seed: Optional[int] = None,
    strict: bool = True,
    use_case: Optional[str] = None,
) -> list[NodeSet]:
    """Return n NodeSets covering every dimension value at least min_coverage times.

    Args:
        taxonomy: dimension → allowed values (from builder.load_taxonomy).
        domain: stored on each NodeSet for downstream traceability.
        n: number of node-sets to produce.
        min_coverage: minimum appearances per value per dimension.
        seed: RNG seed for reproducibility (None = nondeterministic).
        strict: if True, raise CoverageError when n is too small to guarantee
                coverage; if False, sample anyway with reduced coverage.

    The returned list is shuffled so dimensions are not correlated by position.
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    if min_coverage < 1:
        raise ValueError(f"min_coverage must be >= 1, got {min_coverage}")

    rng = random.Random(seed)

    if strict:
        for dim, values in taxonomy.items():
            need = len(values) * min_coverage
            if n < need:
                raise CoverageError(
                    f"n={n} cannot cover dimension '{dim}' "
                    f"({len(values)} values × {min_coverage} = {need} required)"
                )

    columns: dict[str, list[str]] = {
        dim: _build_dim_sequence(values, n, min_coverage, rng)
        for dim, values in taxonomy.items()
    }

    node_sets: list[NodeSet] = []
    for i in range(n):
        dims = {dim: columns[dim][i] for dim in taxonomy}
        node_sets.append(
            NodeSet(
                node_id=f"{domain}-{i:06d}",
                domain=domain,
                dimensions=dims,
                use_case=use_case,
            )
        )

    rng.shuffle(node_sets)
    # Renumber after shuffle so node_id matches final position — easier debugging.
    for i, ns in enumerate(node_sets):
        node_sets[i] = NodeSet(
            node_id=f"{domain}-{i:06d}",
            domain=ns.domain,
            dimensions=ns.dimensions,
            use_case=ns.use_case,
        )
    return node_sets
