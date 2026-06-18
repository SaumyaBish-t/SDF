"""Shared typed records that flow through the asyncio queues.

Every stage consumes one of these and emits the next. Keeping them in one
module avoids circular imports between pipeline stages.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, SecretStr


# ---------------------------------------------------------------------------
# BYOK (Bring-Your-Own-Key) — caller-supplied provider credentials, one per
# pipeline role. Used by the FastAPI request body and CLI --providers file.
# api_key is a SecretStr so it never appears in repr/logs/exception messages.
# ---------------------------------------------------------------------------
class ProviderKey(BaseModel):
    """Credentials + model for one pipeline role (generator / prefilter / scorer)."""
    api_key: SecretStr = Field(..., description="OpenAI-compatible bearer token")
    model: str = Field(..., min_length=1, description="Provider's model identifier")
    base_url: str = Field(..., min_length=1, description="OpenAI-compatible /v1 endpoint")
    batch_size: int = Field(default=4, ge=1, le=32,
                            description="Max concurrent in-flight requests for this role")


class ProviderConfig(BaseModel):
    """Three per-role keys. All three are required when BYOK is used at all —
    partial overrides are rejected to keep cost accountability unambiguous."""
    generator: ProviderKey
    prefilter: ProviderKey
    scorer: ProviderKey


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

    `use_case` is an optional free-form brief for custom (un-predefined) domains
    where the caller describes their data needs in prose instead of (or in
    addition to) a fixed taxonomy file. Generator inlines it into the meta-prompt.
    """
    node_id: str
    domain: str
    dimensions: dict[str, str]
    use_case: Optional[str] = None


class RawExample(BaseModel):
    """Output of generator stage — sits on Queue1."""
    example_id: str
    node_id: str
    prompt: str
    completion: str
    generator_model: str
    generator_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScoredExample(BaseModel):
    """Output of pre_filter stage — sits on Queue2."""
    raw: RawExample
    prefilter_score: float
    prefilter_model: str
    prefilter_key: str


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
