"""
Central configuration for Synthetic Data Forge.

All constants, model strings, thresholds, and key role assignments live here.
Pipeline code MUST import from this module — no magic numbers elsewhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env")


# ---------------------------------------------------------------------------
# NIM endpoint
# ---------------------------------------------------------------------------
NIM_BASE_URL: Final[str] = os.getenv(
    "NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"
)


# ---------------------------------------------------------------------------
# Key role assignments
# Frozen dataclass — role bindings MUST NOT be reassigned at runtime.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class KeyRole:
    name: str           # logical role: generator | pre_filter | full_scorer
    api_key: str        # value loaded from .env
    model: str          # NIM model string
    batch_size: int     # concurrent requests per batch


def _require_env(var: str) -> str:
    val = os.getenv(var)
    if not val:
        raise RuntimeError(
            f"Missing required environment variable: {var}. "
            f"Copy .env.example to .env and fill in your NIM keys."
        )
    return val


KEY_1: Final[KeyRole] = KeyRole(
    name="generator",
    api_key=_require_env("NIM_KEY_1"),
    model="deepseek-ai/deepseek-v4-flash",
    batch_size=10,
)

KEY_2: Final[KeyRole] = KeyRole(
    name="generator",
    api_key=_require_env("NIM_KEY_2"),
    model="z-ai/glm4.7",
    batch_size=10,
)

KEY_3: Final[KeyRole] = KeyRole(
    name="pre_filter",
    api_key=_require_env("NIM_KEY_3"),
    model="nvidia/nemotron-3-nano-30b-a3b",
    batch_size=3,
)

KEY_4: Final[KeyRole] = KeyRole(
    name="pre_filter",
    api_key=_require_env("NIM_KEY_4"),
    model="mistralai/mistral-small-4-119b-2603",
    batch_size=3,
)

KEY_5: Final[KeyRole] = KeyRole(
    name="full_scorer",
    api_key=_require_env("NIM_KEY_5"),
    model="deepseek-ai/deepseek-r1-0528",
    batch_size=1,
)

GENERATOR_KEYS: Final[tuple[KeyRole, ...]] = (KEY_1, KEY_2)
PRE_FILTER_KEYS: Final[tuple[KeyRole, ...]] = (KEY_3, KEY_4)
FULL_SCORER_KEY: Final[KeyRole] = KEY_5

# Per-model sampling temperatures (PROJECT_SPEC.md §5).
# Keyed by KeyRole.model string so generator.py needs no model-name conditionals.
GEN_TEMPERATURE: Final[dict[str, float]] = {
    KEY_1.model: 0.9,
    KEY_2.model: 0.85,
}
GEN_MAX_TOKENS: Final[int] = 4096
GEN_DEFAULT_BATCH_SIZE: Final[int] = 10  # examples per generator call

# Pre-filter critic settings (PROJECT_SPEC.md §6, binary pass/fail rubric).
# Low temperature — we want stable judgment, not creativity.
PREFILTER_TEMPERATURE: Final[float] = 0.2
PREFILTER_MAX_TOKENS: Final[int] = 1024
PREFILTER_PASS_SCORE: Final[float] = 1.0
PREFILTER_FAIL_SCORE: Final[float] = 0.0

# Full scorer (KEY_5, DeepSeek R1) — 1-5 rubric per dimension.
# Weights and dimension names from PROJECT_SPEC.md §6.
FULL_SCORER_TEMPERATURE: Final[float] = 0.0   # deterministic judgment
FULL_SCORER_MAX_TOKENS: Final[int] = 2048     # R1 emits reasoning + JSON

RUBRIC_WEIGHTS: Final[dict[str, float]] = {
    "factuality":          0.30,
    "instruction_clarity": 0.20,
    "response_quality":    0.25,
    "domain_relevance":    0.15,
    "format_compliance":   0.10,
}
RUBRIC_DIMENSIONS: Final[tuple[str, ...]] = tuple(RUBRIC_WEIGHTS.keys())
RUBRIC_SCORE_MIN: Final[int] = 1
RUBRIC_SCORE_MAX: Final[int] = 5

# Storage (PROJECT_SPEC.md §8).
EMBEDDING_DIM: Final[int] = 1024  # nv-embedcode-7b-v1
LANCE_TABLE_NAME: Final[str] = "examples"


# ---------------------------------------------------------------------------
# Quality thresholds
# ---------------------------------------------------------------------------
ACCEPT_THRESHOLD: Final[float] = 3.5
REVISE_RANGE: Final[tuple[float, float]] = (3.0, 3.4)
REJECT_BELOW: Final[float] = 3.0
SIMILARITY_REJECT: Final[float] = 0.92   # cosine similarity ceiling
MINHASH_THRESHOLD: Final[float] = 0.7    # Jaccard similarity for MinHash LSH


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------
QUEUE_RAW_MAXSIZE: Final[int] = 200       # generator -> pre_filter
QUEUE_SCORED_MAXSIZE: Final[int] = 100    # pre_filter -> full_scorer
QUEUE_ACCEPTED_MAXSIZE: Final[int] = 100  # full_scorer -> deduplicator

CHECKPOINT_INTERVAL: Final[int] = 100     # accepted examples per checkpoint


# ---------------------------------------------------------------------------
# Retry / backoff (applies to every API call)
# ---------------------------------------------------------------------------
MAX_RETRIES: Final[int] = 3
BACKOFF_BASE_SECONDS: Final[int] = 2      # delay = BACKOFF_BASE ** attempt


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CHECKPOINT_DIR: Final[Path] = _PROJECT_ROOT / "checkpoints"
LOG_DIR: Final[Path] = _PROJECT_ROOT / "logs"
OUTPUT_DIR: Final[Path] = _PROJECT_ROOT / "output"
LANCEDB_PATH: Final[Path] = _PROJECT_ROOT / "data" / "lancedb"
DUCKDB_PATH: Final[Path] = _PROJECT_ROOT / "data" / "metadata.duckdb"

for _d in (CHECKPOINT_DIR, LOG_DIR, OUTPUT_DIR, LANCEDB_PATH.parent):
    _d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: Final[str] = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: Final[Path] = LOG_DIR / "pipeline.log"
