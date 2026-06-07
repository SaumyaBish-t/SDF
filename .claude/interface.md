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

## pipeline/generator.py
Last updated: Session 5
Purpose: Produce RawExample batches from NIM generator endpoints (KEY_1/KEY_2).
Public API:
  - `parse_json_array(text: str) -> list[dict]`
      Tolerant parser: strips ``` fences, falls back to greedy [...] regex,
      drops non-dict items. Returns [] on total failure (soft retry signal).
  - `build_meta_prompt(node_set: NodeSet, batch_size: int) -> str`
      Renders the PROJECT_SPEC §4 meta-prompt with the NodeSet's dimensions
      embedded as JSON. Tells the model: no markdown, no code fences.
  - `round_robin_keys() -> Iterator[KeyRole]`
      Endless `itertools.cycle` over GENERATOR_KEYS for fair scheduling.
  - `async generate_batch(
        node_set: NodeSet,
        key: KeyRole | None = None,
        batch_size: int | None = None,
    ) -> list[RawExample]`
      One generator call. Wraps the HTTP request in `utils.with_retry`
      (3 attempts, exponential backoff). Bounded by a per-key semaphore
      sized to `KeyRole.batch_size`. Defaults: key=KEY_1, batch_size=
      config.GEN_DEFAULT_BATCH_SIZE. Items missing instruction/response
      are silently skipped; full-batch parse failure logs and returns [].
Queue produced (downstream): `raw_queue` (RawExample). Orchestrator wires
  the call site, not this module.
Module seam for tests: `_make_client(api_key) -> AsyncOpenAI` — monkeypatch
  this to inject a fake client.
Side effects: writes INFO/WARN logs to logger `sdf.generator`. No file IO.
Config touched: GEN_TEMPERATURE, GEN_MAX_TOKENS, GEN_DEFAULT_BATCH_SIZE
  added to config.py (Session 5).

---

## pipeline/critic_prefilter.py
Last updated: Session 6
Purpose: Cheap binary pass/fail scoring on RawExamples (PROJECT_SPEC §6).
  One NIM call scores an entire batch to amortize HTTP overhead.
Public API:
  - `build_prefilter_prompt(examples: Sequence[RawExample], domain: str) -> str`
      Renders the spec §6 rubric with each example numbered by id.
  - `parse_prefilter_response(text: str, batch_len: int) -> dict[int, bool]`
      Tolerant parser for `[{"id":N,"pass":bool},...]`. Accepts 0/1 ints
      for `pass`. Drops out-of-range ids, non-bool/non-{0,1} verdicts,
      malformed items.
  - `round_robin_prefilter_keys() -> Iterator[KeyRole]`
      `cycle(KEY_3, KEY_4)`.
  - `async prefilter_batch(
        examples: Sequence[RawExample],
        domain: str,
        key: KeyRole | None = None,
    ) -> list[ScoredExample]`
      One ScoredExample per input, preserving input order. Examples the
      critic omits → fail (conservative). Empty input short-circuits with
      no API call. Default key=KEY_3. Raises ValueError if a non-prefilter
      key is supplied. Wrapped in `utils.with_retry`; bounded by per-key
      semaphore (KeyRole.batch_size=3 each).
  - `filter_passing(scored: Sequence[ScoredExample]) -> list[ScoredExample]`
      Keep only items at PREFILTER_PASS_SCORE — orchestrator uses between
      scored_queue producers and the full_scorer stage.
Queue produced (downstream): `scored_queue` (ScoredExample). Caller wires.
Module seam for tests: `_make_client(api_key)` — monkeypatch to inject fake.
Reuses: `pipeline.generator.parse_json_array` (shared tolerant array parser).
Side effects: INFO/WARN logs to logger `sdf.critic.prefilter`.
Config touched: PREFILTER_TEMPERATURE, PREFILTER_MAX_TOKENS,
  PREFILTER_PASS_SCORE, PREFILTER_FAIL_SCORE added to config.py (Session 6).

---

