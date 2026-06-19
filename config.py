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


# ---------------------------------------------------------------------------
# Server-side defaults — three role keys read straight from .env.
#
# One block per role: generator, prefilter, scorer. Each role is independent;
# point them at the same provider or three different ones, the system doesn't
# care as long as each base_url is OpenAI-compatible (`/chat/completions`).
#
# Env vars are read with safe empty-string defaults so `import config` never
# fails. Missing values are surfaced by `validate_runtime_keys()` the moment
# a run actually needs them — keeps test collection and `--help` snappy.
#
# BYOK requests (POST /runs with a `providers` block) bypass these entirely.
# ---------------------------------------------------------------------------
def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


# Ollama Cloud — single-provider shortcut. Fill OLLAMA_API_KEY + OLLAMA_MODEL
# in .env and all three roles (generator / prefilter / scorer) reuse them
# unless a per-role SDF_* override is set. Ollama's OpenAI-compatible endpoint
# lives at https://ollama.com/v1 — override via OLLAMA_BASE_URL if needed.
OLLAMA_BASE_URL: Final[str] = _env("OLLAMA_BASE_URL", "https://ollama.com/v1")
OLLAMA_API_KEY: Final[str] = _env("OLLAMA_API_KEY")
OLLAMA_MODEL: Final[str] = _env("OLLAMA_MODEL")


def _role_env(prefix: str, field: str, fallback: str) -> str:
    """Read SDF_<PREFIX>_<FIELD>; fall back to the shared Ollama value."""
    return _env(f"{prefix}_{field}") or fallback


GENERATOR_KEY: Final[KeyRole] = KeyRole(
    name="generator",
    api_key=_role_env("SDF_GENERATOR", "API_KEY", OLLAMA_API_KEY),
    model=_role_env("SDF_GENERATOR", "MODEL", OLLAMA_MODEL),
    batch_size=int(_env("SDF_GENERATOR_BATCH_SIZE", "5")),
    base_url=_role_env("SDF_GENERATOR", "BASE_URL", OLLAMA_BASE_URL),
)

PREFILTER_KEY: Final[KeyRole] = KeyRole(
    name="pre_filter",
    api_key=_role_env("SDF_PREFILTER", "API_KEY", OLLAMA_API_KEY),
    model=_role_env("SDF_PREFILTER", "MODEL", OLLAMA_MODEL),
    batch_size=int(_env("SDF_PREFILTER_BATCH_SIZE", "8")),
    base_url=_role_env("SDF_PREFILTER", "BASE_URL", OLLAMA_BASE_URL),
)

SCORER_KEY: Final[KeyRole] = KeyRole(
    name="full_scorer",
    api_key=_role_env("SDF_SCORER", "API_KEY", OLLAMA_API_KEY),
    model=_role_env("SDF_SCORER", "MODEL", OLLAMA_MODEL),
    batch_size=int(_env("SDF_SCORER_BATCH_SIZE", "4")),
    base_url=_role_env("SDF_SCORER", "BASE_URL", OLLAMA_BASE_URL),
)

# Pools — single-element tuples. The pool shape exists for round-robin over
# multiple keys per role (legacy NIM pattern); BYOK and single-key configs
# just supply one element.
GENERATOR_KEYS: Final[tuple[KeyRole, ...]] = (GENERATOR_KEY,)
PRE_FILTER_KEYS: Final[tuple[KeyRole, ...]] = (PREFILTER_KEY,)
FULL_SCORER_KEY: Final[KeyRole] = SCORER_KEY


def validate_runtime_keys() -> None:
    """Raise with a clear message if any role is missing api_key/model/base_url.

    Called by `orchestrator.run()` and the FastAPI startup. NOT called at
    module import so `--help`, tests, and `cli.py list-domains` still work
    without a populated `.env`.
    """
    missing: list[str] = []
    for role_key, prefix in (
        (GENERATOR_KEY, "SDF_GENERATOR"),
        (PREFILTER_KEY, "SDF_PREFILTER"),
        (SCORER_KEY,    "SDF_SCORER"),
    ):
        for field in ("api_key", "model", "base_url"):
            if not getattr(role_key, field):
                missing.append(f"{prefix}_{field.upper()}")
    if missing:
        raise RuntimeError(
            "Missing required env vars: " + ", ".join(missing) +
            ". Copy .env.example to .env and fill them in."
        )


GEN_TEMPERATURE_DEFAULT: Final[float] = 0.9
# Per-model override map. Add an entry only if you want a specific model to
# sample at something other than GEN_TEMPERATURE_DEFAULT.
GEN_TEMPERATURE: Final[dict[str, float]] = {}
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
QUEUE_RAW_MAXSIZE: Final[int] = 30        # generator -> pre_filter
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
