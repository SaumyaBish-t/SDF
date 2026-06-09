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
BLUESMINDS_BASE_URL: Final[str] = "https://api.bluesminds.com/v1"
BEDROCK_BASE_URL: Final[str] = os.getenv(
    "BEDROCK_BASE_URL", "http://localhost:4000/v1"
)


# ---------------------------------------------------------------------------
# Key role assignments
# Frozen dataclass — role bindings MUST NOT be reassigned at runtime.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class KeyRole:
    name: str           # logical role: generator | pre_filter | full_scorer
    api_key: str        # value loaded from .env (or supplied per request via BYOK)
    model: str          # provider model string
    batch_size: int     # concurrent requests per batch
    base_url: str = NIM_BASE_URL  # OpenAI-compatible endpoint

    def __repr__(self) -> str:  # noqa: D401 — short on purpose
        # api_key is the only sensitive field; everything else is fine to log.
        return (
            f"KeyRole(name={self.name!r}, model={self.model!r}, "
            f"base_url={self.base_url!r}, batch_size={self.batch_size}, "
            f"api_key=***)"
        )


def keyroles_from_provider_config(providers) -> tuple["KeyRole", "KeyRole", "KeyRole"]:
    """Build (generator, prefilter, scorer) KeyRoles from a `models.ProviderConfig`.

    Lives here (not in `models.py`) so models.py stays free of config-layer
    types. `providers` is typed as `Any` to keep this import cycle-free —
    callers pass a `models.ProviderConfig` instance and we read its fields.
    """
    gen = KeyRole(
        name="generator",
        api_key=providers.generator.api_key.get_secret_value(),
        model=providers.generator.model,
        batch_size=providers.generator.batch_size,
        base_url=providers.generator.base_url,
    )
    pre = KeyRole(
        name="pre_filter",
        api_key=providers.prefilter.api_key.get_secret_value(),
        model=providers.prefilter.model,
        batch_size=providers.prefilter.batch_size,
        base_url=providers.prefilter.base_url,
    )
    scr = KeyRole(
        name="full_scorer",
        api_key=providers.scorer.api_key.get_secret_value(),
        model=providers.scorer.model,
        batch_size=providers.scorer.batch_size,
        base_url=providers.scorer.base_url,
    )
    return gen, pre, scr


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
    # Was "z-ai/glm4.7" — retired by NIM on 2026-05-14. Mirroring KEY_1's
    # model lets the second key stay in rotation; semaphores are per-key
    # so total in-flight stays at 20 generator requests.
    model="deepseek-ai/deepseek-v4-flash",
    batch_size=10,
)

KEY_3: Final[KeyRole] = KeyRole(
    name="pre_filter",
    api_key=_require_env("NIM_KEY_3"),
    model="nvidia/nemotron-3-nano-30b-a3b",
    # Bumped 3 → 8: observed ~0.4 RPM on this key in practice, nowhere
    # near the 40 RPM cap. More in-flight requests drain raw_queue faster.
    # Backoff handles any 429 if NIM pushes back.
    batch_size=8,
)

KEY_4: Final[KeyRole] = KeyRole(
    name="pre_filter",
    api_key=_require_env("NIM_KEY_4"),
    model="mistralai/mistral-small-4-119b-2603",
    batch_size=8,
)

KEY_5: Final[KeyRole] = KeyRole(
    name="full_scorer",
    api_key=_require_env("NIM_KEY_5"),
    # nano-8b was fast but sycophantic — every example came back 5/5/5/5/5,
    # so the rubric did no work. Llama-3.3-70b-instruct is the calibration
    # sweet spot: large enough to actually discriminate, instruction-tuned
    # (no reasoning preamble), mainline on NIM. NIM free-tier rate-limit
    # is the wall-clock floor anyway, so the per-call slowdown is hidden.
    model="meta/llama-3.3-70b-instruct",
    # Bumped 3 → 6. The embedder used to share this key — now that local
    # sentence-transformers handles dedup vectors, KEY_5's full budget
    # goes to scoring; raise concurrency to use it.
    batch_size=6,
)

# ---------------------------------------------------------------------------
# Bluesminds keys — kept defined for easy fallback, but BLUESMINDS_KEY is
# now optional. If unset, the KEY_BM_* roles get a dummy key and any attempt
# to actually use them would 401 — which is fine, they're not in the active
# pools below.
# ---------------------------------------------------------------------------
_BM_KEY: Final[str] = os.getenv("BLUESMINDS_KEY", "unset")

KEY_BM_GEN: Final[KeyRole] = KeyRole(
    name="generator",
    api_key=_BM_KEY,
    model="DeepSeek-V4-Flash",   # $0.14 / $0.28 per M — same family as NIM gen
    batch_size=5,
    base_url=BLUESMINDS_BASE_URL,
)

KEY_BM_PREFILTER: Final[KeyRole] = KeyRole(
    name="pre_filter",
    api_key=_BM_KEY,
    model="gpt-5-nano",           # $0.10 / $0.80 — cheapest input, tiny outputs
    batch_size=8,
    base_url=BLUESMINDS_BASE_URL,
)

KEY_BM_SCORER: Final[KeyRole] = KeyRole(
    name="full_scorer",
    api_key=_BM_KEY,
    model="z-ai/glm-5.1",         # $0.60 / $0.18 — reasoning model, cheap output
    batch_size=6,
    base_url=BLUESMINDS_BASE_URL,
)

# ---------------------------------------------------------------------------
# Bedrock keys (via LiteLLM proxy at http://localhost:4000/v1).
# Model strings match the `model_name` entries in litellm_config.yaml.
# Proxy doesn't require auth on localhost — pass a dummy api_key.
# ---------------------------------------------------------------------------
_BR_KEY: Final[str] = "litellm-local"  # proxy ignores this, but openai SDK requires non-empty

KEY_BR_GEN: Final[KeyRole] = KeyRole(
    name="generator",
    api_key=_BR_KEY,
    model="nova-lite",            # Bedrock amazon.nova-lite-v1:0 — $0.06 / $0.24 per M
    batch_size=5,
    base_url=BEDROCK_BASE_URL,
)

KEY_BR_PREFILTER: Final[KeyRole] = KeyRole(
    name="pre_filter",
    api_key=_BR_KEY,
    model="nova-micro",           # Bedrock amazon.nova-micro-v1:0 — $0.035 / $0.14 per M
    batch_size=8,
    base_url=BEDROCK_BASE_URL,
)

KEY_BR_SCORER: Final[KeyRole] = KeyRole(
    name="full_scorer",
    api_key=_BR_KEY,
    model="scorer",               # Bedrock meta.llama3-3-70b-instruct — $0.72 / $0.72 per M
    batch_size=4,
    base_url=BEDROCK_BASE_URL,
)

# Active pools — Bedrock via LiteLLM. Flip back by pointing these at
# (KEY_BM_*,) for bluesminds or (KEY_1, KEY_2) / (KEY_3, KEY_4) / KEY_5 for NIM.
GENERATOR_KEYS: Final[tuple[KeyRole, ...]] = (KEY_BR_GEN,)
PRE_FILTER_KEYS: Final[tuple[KeyRole, ...]] = (KEY_BR_PREFILTER,)
FULL_SCORER_KEY: Final[KeyRole] = KEY_BR_SCORER

# Per-model sampling temperatures (PROJECT_SPEC.md §5).
# Keyed by KeyRole.model string so generator.py needs no model-name conditionals.
GEN_TEMPERATURE: Final[dict[str, float]] = {
    KEY_1.model: 0.9,
    KEY_2.model: 0.85,  # if KEY_1 and KEY_2 share a model, last write wins
    KEY_BM_GEN.model: 0.9,
    KEY_BR_GEN.model: 0.9,
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
# Moved from NIM nv-embedcode-7b-v1 (4096 dim, ~2s API round-trip) to
# local sentence-transformers all-MiniLM-L6-v2 (384 dim, ~50ms CPU). Kills
# ~100 slow API calls per 100-accept run and frees KEY_5 to focus on the
# scorer. Bumping this requires wiping the existing LanceDB table since
# the vector column is a fixed-size list.
EMBEDDING_DIM: Final[int] = 384
LANCE_TABLE_NAME: Final[str] = "examples"

# Local embedding model — sentence-transformers loads it from HuggingFace
# the first time and caches under ~/.cache/huggingface. ~80MB download.
EMBED_MODEL: Final[str] = "sentence-transformers/all-MiniLM-L6-v2"

# Dedup — MinHash LSH layer (PROJECT_SPEC §7).
MINHASH_NUM_PERM: Final[int] = 128
MINHASH_NGRAM_SIZE: Final[int] = 5


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
