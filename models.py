"""Shared typed records that flow through the asyncio queues.

Every stage consumes one of these and emits the next. Keeping them in one
module avoids circular imports between pipeline stages.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TaxonomyNode(BaseModel):
    """Single node in the seed taxonomy tree (hierarchical view)."""
    node_id: str
    domain: str
    topic: str
    subtopic: Optional[str] = None
    depth: int


class NodeSet(BaseModel):
    """One sampled scenario — a value chosen for each taxonomy dimension.

    Produced by the seed sampler, consumed by the generator's meta-prompt.
    `dimensions` example: {"topic": "billing_dispute", "tone": "frustrated", ...}
    """
    node_id: str
    domain: str
    dimensions: dict[str, str]


class RawExample(BaseModel):
    """Output of generator stage — sits on Queue1."""
    example_id: str
    node_id: str
    prompt: str
    completion: str
    generator_model: str
    generator_key: Literal["KEY_1", "KEY_2"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScoredExample(BaseModel):
    """Output of pre_filter stage — sits on Queue2."""
    raw: RawExample
    prefilter_score: float
    prefilter_model: str
    prefilter_key: Literal["KEY_3", "KEY_4"]


class JudgedExample(BaseModel):
    """Output of full_scorer stage — sits on Queue3 if accepted."""
    scored: ScoredExample
    full_score: float
    rubric: dict
    verdict: Literal["accept", "revise", "reject"]


class AcceptedExample(BaseModel):
    """Final record persisted to DuckDB + LanceDB and emitted to JSONL."""
    judged: JudgedExample
    embedding: list[float]
    minhash_signature: list[int]
