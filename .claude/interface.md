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

## pipeline/critic_scorer.py
Last updated: Session 7
Purpose: Full rubric scoring with KEY_5 (DeepSeek R1) per PROJECT_SPEC §6.
  Scores one ScoredExample at a time (KEY_5.batch_size=1).
Public API:
  - `build_scorer_prompt(scored: ScoredExample, domain: str) -> str`
      Spec §6 prompt: 1-5 rubric across RUBRIC_DIMENSIONS, reject criteria,
      what earns a 5. Includes the example's prompt + completion.
  - `parse_rubric(text: str) -> dict[str, int]`
      Strips ``` fences, json.loads with greedy `{...}` regex fallback.
      Clamps scores to [RUBRIC_SCORE_MIN, RUBRIC_SCORE_MAX]. Drops bool
      values (subclass of int — would otherwise sneak through), non-numeric
      values, and unknown dimension keys. Missing dims omitted (caller
      decides — `composite_score` treats missing as 0).
  - `composite_score(rubric: dict[str, int]) -> float`
      Weighted sum using config.RUBRIC_WEIGHTS. Missing dims = 0
      (deliberate — incomplete rubric ⇒ low composite ⇒ likely reject).
  - `verdict_for(score: float) -> Literal["accept","revise","reject"]`
      `>= ACCEPT_THRESHOLD` → accept; `[REVISE_RANGE[0], REVISE_RANGE[1]]`
      → revise; otherwise reject. Both boundaries inclusive.
  - `async full_score(scored: ScoredExample, domain: str) -> JudgedExample`
      One API call wrapped in `utils.with_retry`. On parse failure after
      retries: returns JudgedExample with full_score=0.0, rubric={},
      verdict="reject" (unscorable == rejected). Bounded by module-level
      semaphore sized to KEY_5.batch_size (=1).
Queue produced (downstream): `accepted_queue` (JudgedExample where
  verdict='accept'); orchestrator may also route 'revise' to a revise_queue.
Module seam for tests: `_make_client(api_key)` — monkeypatch to inject fake.
Side effects: INFO/WARN logs to logger `sdf.critic.scorer`.
Config touched: FULL_SCORER_TEMPERATURE, FULL_SCORER_MAX_TOKENS,
  RUBRIC_WEIGHTS, RUBRIC_DIMENSIONS, RUBRIC_SCORE_MIN/MAX added (Session 7).

---

## storage/store.py
Last updated: Session 8
Purpose: Persistence layer — DuckDB for metadata + analytics, LanceDB for
  vector storage + semantic-dedup queries (PROJECT_SPEC §8).
  Both libs are sync; all calls run inside `asyncio.to_thread` so the
  orchestrator's event loop is not blocked on disk IO.
Public API:
  - `Store(duckdb_path=None, lancedb_path=None, embedding_dim=None)`
      Defaults from config.DUCKDB_PATH / LANCEDB_PATH / EMBEDDING_DIM.
      Use as `async with Store() as store: ...`; or call `await
      store.open()` / `await store.close()` explicitly.
  - `async write(accepted: AcceptedExample, taxonomy_node: dict[str, str])`
      Inserts one row in DuckDB and one record in LanceDB. The
      `taxonomy_node` dict MUST include a `"domain"` key (orchestrator
      composes it from NodeSet.domain + NodeSet.dimensions). Raises
      `ValueError` on embedding-dim mismatch.
  - `async nearest_similarity(embedding: list[float]) -> float`
      Returns 0.0 on empty store; otherwise `1/(1+distance)` for the
      closest vector — monotonic proxy in (0, 1] for threshold checks.
      Raises ValueError on dim mismatch.
  - `async count(domain: str | None = None) -> int`
  - `async coverage(domain: str, dimension: str) -> dict[str, int]`
      {taxonomy_value: count} via DuckDB json_extract — for the
      coverage checker / orchestrator's gap analysis.
  - `async all_embeddings(domain: str | None = None) -> list[list[float]]`
      For the Vendi Score diversity tracker — not the dedup hot path.
DuckDB schema (table `examples`): id, domain, instruction, response,
  composite_score, verdict, rubric_json, taxonomy_node_json,
  generator_model, generator_key, prefilter_key, prefilter_score, timestamp.
LanceDB schema (table `examples`): id, domain, vector(fixed-size float32[dim]),
  composite_score. Minimal — rich metadata lives in DuckDB.
Side effects:
  - Creates `config.DUCKDB_PATH.parent` and `config.LANCEDB_PATH` directories.
  - Writes log lines to logger `sdf.store`.
Config touched: EMBEDDING_DIM=1024, LANCE_TABLE_NAME="examples" (Session 8).
LanceDB API note: `list_tables()` may return either a plain list (~0.13)
  or a `ListTablesResponse(tables=...)` object (>=0.33). _open_sync handles
  both forms; revisit if pinning newer versions.

---

## pipeline/deduplicator.py
Last updated: Session 9
Purpose: Two-layer dedup before persistence (PROJECT_SPEC §7).
  Layer 1: MinHash LSH on 5-grams (num_perm=128, Jaccard ≥ 0.7).
  Layer 2: embedding via nv-embedcode-7b-v1 → LanceDB cosine
           (similarity ≥ 0.92 rejects).
Public API:
  - `get_ngrams(text: str, n: int = 5) -> list[str]`
      Lowercased character n-grams; short text → one token.
  - `make_minhash(text, num_perm=128, n=5) -> MinHash`
  - `signature_to_list(m: MinHash) -> list[int]`
      Pydantic-friendly serialization for AcceptedExample.minhash_signature.
  - `Deduplicator(store, num_perm=..., ngram_size=..., minhash_threshold=...,
                  similarity_reject=..., embed_model=..., embed_api_key=...)`
      All thresholds default from config. Holds in-memory MinHashLSH.
  - `async Deduplicator.embed(text) -> list[float]`
      One NIM `embeddings.create` call wrapped in `utils.with_retry`.
  - `async Deduplicator.check(judged: JudgedExample) -> AcceptedExample | None`
      Returns None on either-layer duplicate; AcceptedExample with embedding
      + minhash_signature on survival. Raises ValueError on dim mismatch.
      Does NOT mutate the LSH index — caller must call `register(...)`
      after persisting so commit order stays explicit.
  - `Deduplicator.register(example_id: str, text: str) -> None`
      Idempotent insert into the LSH index.
  - `Deduplicator.minhash_rejects / cosine_rejects / accepted: int`
      Per-instance counters for orchestrator logging.
Queue produced (downstream): `accepted_queue` (AcceptedExample); writer consumes.
Module seam for tests: `_make_client(api_key)` — monkeypatch to inject fake.
Side effects: INFO logs to logger `sdf.dedup`. No file IO (Store handles disk).
Config touched: EMBED_MODEL, EMBED_API_KEY_ROLE, MINHASH_NUM_PERM,
  MINHASH_NGRAM_SIZE added to config.py (Session 9).
Threading: MinHashLSH is not thread-safe; runs on a single consumer task.

---

## pipeline/writer.py
Last updated: Session 10
Purpose: HuggingFace-compatible JSONL output per PROJECT_SPEC §9.
Public API:
  - `render_record(
        accepted: AcceptedExample,
        taxonomy_node: dict[str, str],
        *, nearest_neighbor_similarity: float | None = None,
        generation_pass: int = 1,
        difficulty_level: int | None = None,
        reasoning_trace: str | None = None,
        timestamp: datetime | None = None,
    ) -> dict`
      Pure function. Returns the HF-shaped dict (top-level: id, instruction,
      response, reasoning_trace, metadata). Default timestamp is now-UTC,
      formatted `YYYY-MM-DDTHH:MM:SSZ`.
  - `async write_jsonl(accepted, path, taxonomy_node, **render_kwargs) -> None`
      Appends one JSON line to `path`. Creates parent dirs. UTF-8 with
      `ensure_ascii=False` so Indic/CJK survives. File IO via
      `asyncio.to_thread`.
Output schema (top-level keys): id, instruction, response, reasoning_trace,
  metadata{taxonomy_node, generator_model, critic_scores, composite_score,
  nearest_neighbor_similarity, generation_pass, difficulty_level, timestamp}.
Side effects: writes to disk; debug log to `sdf.writer`.

---

## pipeline/checkpoint.py
Last updated: Session 10
Purpose: Per-run progress snapshots per PROJECT_SPEC §10. One file per save
  (never overwritten) so a corrupt write can't destroy the last good state.
Public API:
  - `make_run_id(domain: str, when: datetime | None = None) -> str`
      Format: `run_{YYYYmmdd_HHMMSS}_{sanitized_domain}`. Domain
      sanitization replaces any char outside `[A-Za-z0-9_-]` with `_`.
  - `async save_checkpoint(
        run_id: str, domain: str,
        accepted_count: int, last_node_idx: int,
        *, target: int | None = None,
        rejected_count: int = 0,
        vendi_score: float | None = None,
        taxonomy_coverage: dict[str, int] | None = None,
        extra: dict | None = None,
        directory: Path | None = None,
    ) -> Path`
      Writes `{run_id}__{accepted_count:06d}.json` atomically (stage as
      `.tmp`, then rename). Raises ValueError on unsafe run_id chars.
      Default directory = config.CHECKPOINT_DIR.
  - `async load_latest(domain: str | None = None, directory: Path | None = None)
        -> dict | None`
      Newest checkpoint by mtime; optional `domain` filter via filename
      suffix match. Returns None on empty dir or unreadable JSON
      (logged, not raised).
Checkpoint payload keys: run_id, domain, target, accepted_count,
  rejected_count, last_node_idx, vendi_score, taxonomy_coverage, timestamp,
  extra (optional).
Side effects: writes to disk; INFO log to `sdf.checkpoint`.

---

## pipeline/orchestrator.py
Last updated: Session 11
Purpose: Wires every stage through the three asyncio.Queues. Owns task
  lifecycle, backpressure, graceful shutdown, checkpoint cadence, and
  resume-from-checkpoint.
Public API:
  - `async run(
        domain: str,
        target: int,
        *,
        output_path: Path | None = None,
        seed: int | None = None,
        min_coverage: int = 3,
        gen_batch_size: int | None = None,
        n_scorer_workers: int = 2,
        n_prefilter_workers: int = 2,
        resume: bool = True,
    ) -> dict`
      Loads taxonomy, samples node_sets (3 × target with min-coverage),
      optionally resumes from `checkpoint.load_latest(domain)`. Launches:
        * 2 generator workers (one per GENERATOR_KEYS entry, semaphore-bounded
          inside generator.py)
        * `n_prefilter_workers` prefilter workers (alternating KEY_3/KEY_4 via
          `round_robin_prefilter_keys`, each drains raw_queue into batches of
          up to 3 before one prefilter call)
        * `n_scorer_workers` scorer workers calling `full_score` (KEY_5)
        * 1 dedup+writer task (single consumer — MinHashLSH is not thread-safe)
      Shutdown: dedup writer sets `stop_event` on hitting `target`; sentinel
      objects propagate through each queue so consumers exit cleanly.
      Returns: {run_id, domain, target, accepted, rejected, last_node_idx,
      output_path}.
Queue wiring:
  raw_queue (RawExample) → scored_queue (ScoredExample, only PASS) →
  accepted_queue (JudgedExample where verdict='accept').
Checkpoint cadence: every `config.CHECKPOINT_INTERVAL` accepts AND once at
  the end of every run (success, target-hit, or exhaustion).
Output: JSONL via `pipeline.writer.write_jsonl`; default path
  `config.OUTPUT_DIR / {run_id}.jsonl`.
Resume semantics: if a checkpoint for `domain` exists and `resume=True`,
  reuses the same run_id, starts `_NodeSetCursor` at `last_node_idx + 1`,
  and pre-seeds the counters. If already at target, returns immediately
  without opening the store or writing JSONL.
Module seams for tests: `generate_batch`, `prefilter_batch`, `full_score`,
  `Store`, `Deduplicator` are all looked up via module attribute, so they
  can be monkeypatched on `pipeline.orchestrator`.
Side effects: opens Store (DuckDB+LanceDB), writes JSONL + checkpoints,
  logs to `sdf.orchestrator` + child loggers per stage.

---

