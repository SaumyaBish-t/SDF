"""Seed sampler — draws taxonomy nodes for the generator to expand.

Walks the tree from taxonomy_builder and yields nodes in a round-robin order
that keeps coverage balanced across domains/topics.
"""
from __future__ import annotations

from typing import AsyncIterator

from models import TaxonomyNode


async def sample_nodes(taxonomy: list[TaxonomyNode]) -> AsyncIterator[TaxonomyNode]:
    raise NotImplementedError
