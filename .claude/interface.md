# Module Interface Contracts

> Updated at end of every Cowork session.
> Read this file at the start of every session alongside CLAUDE.md.
> Never delete entries — mark deprecated ones with [DEPRECATED].

---

## config.py
Last updated: Session 1
Purpose: Single source of truth for all constants.
Import pattern: `from config import KEY_1, ACCEPT_THRESHOLD, GEN_MODEL_1`
Never import directly from .env anywhere except config.py.

---

## utils.py
Last updated: Session 2
Purpose: Cross-cutting helpers — exponential-backoff retry + file logging.
Public API:
  - `setup_logging() -> logging.Logger`
      Returns the "sdf" logger. Idempotent. Configures a RotatingFileHandler
      writing to `config.LOG_FILE` (10MB × 5 backups, UTF-8). Sets
      `propagate=False` so nothing leaks to stdout.
  - `with_retry(fn, *args, _op_name: str | None = None, **kwargs) -> T`
      Async retry wrapper. Up to `config.MAX_RETRIES` attempts, sleeps
      `config.BACKOFF_BASE_SECONDS ** attempt` between tries. Logs every
      failure to logger `sdf.retry` (warning per retry, error on final).
      Re-raises the last exception when all attempts fail.
Import pattern:
  `from utils import with_retry, setup_logging`
Side effects: creates `logs/` directory if absent; writes to `logs/pipeline.log`.
Logger names used by pipeline code: child loggers under "sdf.*"
  (e.g. "sdf.generator", "sdf.critic.prefilter").

---

## pipeline/queues.py
Last updated: Session 3
Purpose: Typed, bounded asyncio.Queue factories for the three pipeline boundaries.
Public API:
  - `make_raw_queue() -> asyncio.Queue[RawExample]`        (maxsize=QUEUE_RAW_MAXSIZE)
  - `make_scored_queue() -> asyncio.Queue[ScoredExample]`  (maxsize=QUEUE_SCORED_MAXSIZE)
  - `make_accepted_queue() -> asyncio.Queue[JudgedExample]` (maxsize=QUEUE_ACCEPTED_MAXSIZE)
Queue schema (item types):
  - raw_queue       : RawExample      (generator → pre_filter)
  - scored_queue    : ScoredExample   (pre_filter → full_scorer)
  - accepted_queue  : JudgedExample   (full_scorer → deduplicator/writer)
Backpressure: bounded queues block on `put()` when full — slow downstream
  throttles upstream automatically. Sizes come from config; do not pass
  literals here.
Side effects: none.

---

## models.py
Last updated: Session 4 (added NodeSet)
Public types (pydantic BaseModel):
  - `TaxonomyNode(node_id, domain, topic, subtopic, depth)` — hierarchical view (unused so far).
  - `NodeSet(node_id, domain, dimensions: dict[str, str])` — one sampled scenario.
  - `RawExample(example_id, node_id, prompt, completion, generator_model, generator_key, created_at)`
  - `ScoredExample(raw: RawExample, prefilter_score, prefilter_model, prefilter_key)`
  - `JudgedExample(scored: ScoredExample, full_score, rubric: dict, verdict: Literal["accept","revise","reject"])`
  - `AcceptedExample(judged: JudgedExample, embedding: list[float], minhash_signature: list[int])`
Import pattern: `from models import NodeSet, RawExample, ...`

---

## taxonomy/builder.py
Last updated: Session 4
Purpose: Load and validate per-domain taxonomy JSON files. Deterministic, offline.
Public API:
  - `Taxonomy = dict[str, list[str]]` (type alias)
  - `load_taxonomy(domain: str, domains_dir: Path | None = None) -> Taxonomy`
      Reads `{domains_dir}/{domain}.json` (default: `taxonomy/domains/`).
      Validates: dict, non-empty, every dim → non-empty list of unique non-empty strings.
      Raises `TaxonomyError` on any structural problem.
  - `list_domains(domains_dir: Path | None = None) -> list[str]`
      Sorted list of available domain names (file stems).
  - `TaxonomyError(ValueError)`
Files: ships `taxonomy/domains/customer_support.json` as a working example.
Side effects: none (read-only).

---

## taxonomy/seed_sampler.py
Last updated: Session 4
Purpose: Draw N NodeSets with minimum-coverage guarantee per dimension value.
Public API:
  - `sample_node_sets(
        taxonomy: Taxonomy,
        domain: str,
        n: int,
        min_coverage: int = 3,
        seed: int | None = None,
        strict: bool = True,
    ) -> list[NodeSet]`
      Returns n NodeSets, each with one value per dimension. Guarantees every
      value in every dimension appears ≥ min_coverage times. Final list is
      shuffled and node_ids renumbered `{domain}-{idx:06d}` to match position.
      Raises `CoverageError` if `strict=True` and n < len(values)*min_coverage
      for any dim. Raises `ValueError` for non-positive n / min_coverage < 1.
  - `CoverageError(ValueError)`
Algorithm: per-dim "required pool" (each value × min_coverage), shuffled,
  consumed first; remainder filled by uniform random choice. Dimensions
  sampled independently.
Determinism: pass `seed` for reproducible runs.
Side effects: none.

---

